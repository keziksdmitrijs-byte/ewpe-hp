"""The hot water tank."""

from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import STATE_HEAT_PUMP, WaterHeaterEntity, WaterHeaterEntityFeature
from homeassistant.const import ATTR_TEMPERATURE, STATE_OFF, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import POW, TANK_SET, TANK_TEMPERATURE
from .coordinator import EwpeConfigEntry, UnitCoordinator, temperature
from .entity import UnitEntity, reporting


async def async_setup_entry(
    hass: HomeAssistant, entry: EwpeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(Tank(coordinator) for coordinator in reporting(entry, TANK_SET))


class Tank(UnitEntity, WaterHeaterEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = WaterHeaterEntityFeature.TARGET_TEMPERATURE
    _attr_min_temp = 20
    _attr_max_temp = 60
    _attr_target_temperature_step = 1

    def __init__(self, coordinator: UnitCoordinator) -> None:
        super().__init__(coordinator, "tank")

    @property
    def current_operation(self) -> str:
        """The tank is heated by the heat pump while the unit is on."""
        return STATE_HEAT_PUMP if self.coordinator.data.get(POW) else STATE_OFF

    @property
    def current_temperature(self) -> float | None:
        return temperature(self.coordinator.data, TANK_TEMPERATURE)

    @property
    def target_temperature(self) -> float | None:
        return self.coordinator.data.get(TANK_SET)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if (value := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.send({TANK_SET: round(value)})
