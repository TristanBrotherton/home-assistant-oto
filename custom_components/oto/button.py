"""Button platform for OTO."""

from __future__ import annotations

from contextlib import suppress

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OtoCoordinator
from .entity import OtoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[OtoCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up zone Water buttons."""
    coordinator = entry.runtime_data
    async_add_entities(
        OtoZoneWaterButton(coordinator, device_id, zone.id, zone.name)
        for device_id, device in coordinator.data.devices.items()
        for zone in device.zones
    )


class OtoZoneWaterButton(OtoEntity, ButtonEntity):
    """Start watering one discovered OTO zone."""

    _attr_icon = "mdi:sprinkler"

    def __init__(
        self, coordinator: OtoCoordinator, device_id: str, zone_id: str, zone_name: str
    ) -> None:
        super().__init__(coordinator, device_id)
        self.zone_id = zone_id
        self.zone_name = zone_name
        self._attr_name = f"Water {zone_name}"
        self._attr_unique_id = f"{device_id}_{zone_id}_water"

    async def async_press(self) -> None:
        """Start the zone with its paired depth setting."""
        registry = er.async_get(self.hass)
        depth_unique_id = f"{self.device_id}_{self.zone_id}_depth"
        depth_entity_id = registry.async_get_entity_id("number", "oto", depth_unique_id)
        depth = 1.0
        if depth_entity_id and (state := self.hass.states.get(depth_entity_id)):
            with suppress(TypeError, ValueError):
                depth = float(state.state)
        await self.coordinator.async_start_zone(self.device_id, self.zone_id, depth)
