"""Measured temperatures and the error code."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ERROR
from .coordinator import EwpeConfigEntry, UnitCoordinator, temperature
from .entity import UnitEntity, reporting

TEMPERATURE_SENSORS = (
    ("water_outlet", "AllOutWatTem"),
    ("water_inlet", "AllInWatTem"),
    ("heat_pump_outlet", "HepOutWatTem"),
    ("tank_temperature", "WatBoxTem"),
    ("room_temperature", "RmoHomTem"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EwpeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    entities: list[SensorEntity] = [
        Temperature(coordinator, key, name)
        for key, name in TEMPERATURE_SENSORS
        for coordinator in reporting(entry, f"{name}Hi", f"{name}Lo")
        # a sensor that is not fitted reads -30 °C from the start
        if temperature(coordinator.data, name) is not None
    ]
    entities += [ErrorCode(coordinator) for coordinator in reporting(entry, ERROR)]
    async_add_entities(entities)


class Temperature(UnitEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: UnitCoordinator, key: str, name: str) -> None:
        super().__init__(coordinator, key)
        self._name = name

    @property
    def native_value(self) -> float | None:
        return temperature(self.coordinator.data, self._name)


class ErrorCode(UnitEntity, SensorEntity):
    """The unit's error number, 0 when there is none."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: UnitCoordinator) -> None:
        super().__init__(coordinator, "error_code")

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.get(ERROR)
