"""Binary sensor platform for OTO."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import OtoCoordinator
from .entity import OtoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[OtoCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up OTO watering sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        OtoWateringSensor(coordinator, device_id) for device_id in coordinator.data.devices
    )


class OtoWateringSensor(OtoEntity, BinarySensorEntity):
    """Report truthful device-level watering activity."""

    _attr_name = "Watering"
    _attr_icon = "mdi:sprinkler-variant"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    def __init__(self, coordinator: OtoCoordinator, device_id: str) -> None:
        super().__init__(coordinator, device_id)
        self._attr_unique_id = f"{device_id}_watering"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.devices[self.device_id].watering
