"""Diagnostics for OTO."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .coordinator import OtoCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[OtoCoordinator]
) -> dict[str, Any]:
    """Return diagnostics without account, device, zone, or location identifiers."""
    coordinator = entry.runtime_data
    devices = list(coordinator.data.devices.values()) if coordinator.data else []
    return {
        "integration_version": 1,
        "last_update_success": coordinator.last_update_success,
        "device_count": len(devices),
        "devices": [
            {
                "zone_count": len(device.zones),
                "watering": device.watering,
                "firmware_version": device.firmware_version,
            }
            for device in devices
        ],
    }
