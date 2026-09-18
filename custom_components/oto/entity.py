"""Shared OTO entity helpers."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OtoCoordinator


class OtoEntity(CoordinatorEntity[OtoCoordinator]):
    """Base OTO controller entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: OtoCoordinator, device_id: str) -> None:
        super().__init__(coordinator)
        self.device_id = device_id

    @property
    def device_info(self) -> DeviceInfo:
        device = self.coordinator.data.devices[self.device_id]
        return DeviceInfo(
            identifiers={(DOMAIN, self.device_id)},
            name=device.name,
            manufacturer="OTO",
            model="Smart Sprinkler",
            sw_version=device.firmware_version,
        )
