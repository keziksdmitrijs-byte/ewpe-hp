"""Water and room setpoints. The tank's own setpoint is on its water heater entity."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import COOL_WATER_SET, HEAT_WATER_SET, ROOM_COOL_SET, ROOM_HEAT_SET
from .coordinator import EwpeConfigEntry, UnitCoordinator
from .entity import UnitEntity, reporting

# key, parameter, lowest, highest: the ranges of the Versati controller
SETPOINTS = (
    ("heating_water_setpoint", HEAT_WATER_SET, 20, 60),
    ("cooling_water_setpoint", COOL_WATER_SET, 5, 25),
    ("room_heating_setpoint", ROOM_HEAT_SET, 16, 30),
    ("room_cooling_setpoint", ROOM_COOL_SET, 18, 30),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EwpeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(
        Setpoint(coordinator, key, name, low, high)
        for key, name, low, high in SETPOINTS
        for coordinator in reporting(entry, name)
    )


class Setpoint(UnitEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: UnitCoordinator, key: str, name: str, low: int, high: int) -> None:
        super().__init__(coordinator, key)
        self._name = name
        self._attr_native_min_value = low
        self._attr_native_max_value = high

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get(self._name)

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.send({self._name: round(value)})
