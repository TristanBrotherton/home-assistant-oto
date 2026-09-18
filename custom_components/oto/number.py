"""Number platform for OTO watering depth."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_WATERING_DEPTH,
    DEFAULT_WATERING_DEPTH_MM,
    MAX_WATERING_DEPTH_MM,
    MIN_WATERING_DEPTH_MM,
)
from .coordinator import OtoCoordinator
from .entity import OtoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[OtoCoordinator],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up zone depth controls."""
    coordinator = entry.runtime_data
    async_add_entities(
        OtoZoneDepthNumber(coordinator, device_id, zone.id, zone.name)
        for device_id, device in coordinator.data.devices.items()
        for zone in device.zones
    )


class OtoZoneDepthNumber(OtoEntity, NumberEntity, RestoreEntity):
    """Watering depth used by a zone's Water button."""

    _attr_icon = "mdi:water"
    _attr_native_min_value = MIN_WATERING_DEPTH_MM
    _attr_native_max_value = MAX_WATERING_DEPTH_MM
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: OtoCoordinator, device_id: str, zone_id: str, zone_name: str
    ) -> None:
        super().__init__(coordinator, device_id)
        self.zone_id = zone_id
        self._attr_name = f"{zone_name} depth"
        self._attr_unique_id = f"{device_id}_{zone_id}_depth"
        self._attr_native_value = float(
            coordinator.config_entry.options.get(CONF_WATERING_DEPTH, DEFAULT_WATERING_DEPTH_MM)
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last per-zone depth."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                restored = float(last_state.state)
            except (TypeError, ValueError):
                return
            if self.native_min_value <= restored <= self.native_max_value:
                self._attr_native_value = restored

    async def async_set_native_value(self, value: float) -> None:
        """Set the depth used by the Water button."""
        self._attr_native_value = round(value, 1)
        self.async_write_ha_state()
