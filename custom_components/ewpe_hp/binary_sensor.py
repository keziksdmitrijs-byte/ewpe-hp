"""Electric heaters and frost protection running, and whether the unit reports an error."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ERROR
from .coordinator import EwpeConfigEntry, UnitCoordinator
from .entity import UnitEntity, reporting

STATES = (
    ("tank_heater", "WatBoxElcHeRunSta", BinarySensorDeviceClass.RUNNING),
    ("heater_1", "ElcHe1RunSta", BinarySensorDeviceClass.RUNNING),
    ("heater_2", "ElcHe2RunSta", BinarySensorDeviceClass.RUNNING),
    ("frost_protection", "AnFrzzRunSta", BinarySensorDeviceClass.RUNNING),
    ("system_frost_protection", "SyAnFroRunSta", BinarySensorDeviceClass.RUNNING),
    ("problem", ERROR, BinarySensorDeviceClass.PROBLEM),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EwpeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(
        State(coordinator, key, name, device_class)
        for key, name, device_class in STATES
        for coordinator in reporting(entry, name)
    )


class State(UnitEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: UnitCoordinator, key: str, name: str, device_class: BinarySensorDeviceClass) -> None:
        super().__init__(coordinator, key)
        self._name = name
        self._attr_device_class = device_class

    @property
    def is_on(self) -> bool | None:
        value = self.coordinator.data.get(self._name)
        return None if value is None else bool(value)
