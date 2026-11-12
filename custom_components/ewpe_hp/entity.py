"""What every entity of a unit shares."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EwpeConfigEntry, UnitCoordinator


class UnitEntity(CoordinatorEntity[UnitCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: UnitCoordinator, key: str) -> None:
        super().__init__(coordinator)
        unit = coordinator.unit
        self._attr_unique_id = f"{unit.mac}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unit.mac)},
            connections={(CONNECTION_NETWORK_MAC, unit.mac)} if len(unit.mac) == 12 else set(),
            manufacturer="GREE",
            model=unit.model or "Versati",
            name=unit.name,
            sw_version=unit.version,
        )


def reporting(entry: EwpeConfigEntry, *names: str) -> list[UnitCoordinator]:
    """Units that report every one of these parameters."""
    return [
        coordinator
        for coordinator in entry.runtime_data.units
        if coordinator.data is not None and all(name in coordinator.data for name in names)
    ]
