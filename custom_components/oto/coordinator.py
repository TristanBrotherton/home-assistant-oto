"""Data coordinator for OTO."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OtoApiClient, OtoAuthError, OtoConnectionError, OtoDevice, OtoError
from .const import COMMAND_COOLDOWN_SECONDS, DOMAIN


@dataclass(slots=True)
class OtoData:
    """Coordinator data."""

    devices: dict[str, OtoDevice]


class OtoCoordinator(DataUpdateCoordinator[OtoData]):
    """Coordinate OTO cloud reads and serialized watering commands."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: OtoApiClient,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            logger=__import__("logging").getLogger(__name__),
            name=DOMAIN,
            update_interval=update_interval,
            config_entry=entry,
        )
        self.client = client
        self._command_locks: dict[str, asyncio.Lock] = {}
        self._last_command: dict[str, float] = {}

    async def _async_update_data(self) -> OtoData:
        try:
            devices = await self.client.async_get_devices()
        except OtoAuthError as err:
            raise ConfigEntryAuthFailed from err
        except (OtoConnectionError, OtoError) as err:
            raise UpdateFailed(str(err)) from err
        return OtoData(devices={device.id: device for device in devices})

    async def async_start_zone(self, device_id: str, zone_id: str, depth_mm: float) -> None:
        """Start watering once, with per-device serialization and cooldown."""
        lock = self._command_locks.setdefault(device_id, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            if now - self._last_command.get(device_id, 0) < COMMAND_COOLDOWN_SECONDS:
                raise HomeAssistantError("Please wait before sending another watering command")
            device = self.data.devices.get(device_id) if self.data else None
            if device is None or not any(zone.id == zone_id for zone in device.zones):
                raise HomeAssistantError("This OTO zone is no longer available")
            if device.watering:
                raise HomeAssistantError("OTO is already watering")
            self._last_command[device_id] = now
            try:
                await self.client.async_start_zone(device_id, zone_id, depth_mm)
            except OtoAuthError as err:
                raise ConfigEntryAuthFailed from err
            except OtoError as err:
                # Never retry: a timeout is ambiguous and may already have
                # scheduled watering on OTO's backend.
                raise HomeAssistantError(str(err)) from err
            finally:
                await self.async_request_refresh()
            for delay in (5, 15, 30):
                async_call_later(self.hass, delay, self._async_delayed_refresh)

    async def _async_delayed_refresh(self, _now: object) -> None:
        """Refresh after OTO has had time to dispatch a manual event."""
        await self.async_request_refresh()
