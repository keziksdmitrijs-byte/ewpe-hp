"""GREE air conditioners of the Gree+ account."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    AC_FAN,
    AC_FANS,
    AC_MODES,
    AC_ROOM,
    AC_ROOM_OFFSET,
    AC_SET,
    AC_SWING_H,
    AC_SWING_V,
    AIR_CONDITIONER,
    MOD,
    POW,
)
from .coordinator import EwpeConfigEntry, UnitCoordinator
from .entity import UnitEntity, reporting

SWINGS = {"off": (0, 0), "vertical": (1, 0), "horizontal": (0, 1), "both": (1, 1)}


async def async_setup_entry(
    hass: HomeAssistant, entry: EwpeConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(AirConditioner(coordinator) for coordinator in reporting(entry, POW, MOD, AC_SET, kind=AIR_CONDITIONER))


class AirConditioner(UnitEntity, ClimateEntity):
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_target_temperature_step = 1

    def __init__(self, coordinator: UnitCoordinator) -> None:
        super().__init__(coordinator, "air_conditioner")
        # the device's own name; the key only translates the fan speeds
        self._attr_hvac_modes = [HVACMode.OFF, *(HVACMode(mode) for mode in AC_MODES)]
        self._attr_fan_modes = list(AC_FANS)
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.FAN_MODE
        )
        if AC_SWING_V in coordinator.data:
            features |= ClimateEntityFeature.SWING_MODE
            self._attr_swing_modes = list(SWINGS) if AC_SWING_H in coordinator.data else ["off", "vertical"]
        self._attr_supported_features = features

    @property
    def _values(self) -> dict[str, Any]:
        return self.coordinator.data

    @property
    def hvac_mode(self) -> HVACMode | None:
        if not self._values.get(POW):
            return HVACMode.OFF
        mode = next((name for name, number in AC_MODES.items() if number == self._values.get(MOD)), None)
        return HVACMode(mode) if mode else None

    @property
    def current_temperature(self) -> float | None:
        value = self._values.get(AC_ROOM)
        if not isinstance(value, int | float) or value == 0:
            return None
        return value - AC_ROOM_OFFSET if value > 50 else value

    @property
    def target_temperature(self) -> float | None:
        return self._values.get(AC_SET)

    @property
    def fan_mode(self) -> str | None:
        return next((name for name, number in AC_FANS.items() if number == self._values.get(AC_FAN)), None)

    @property
    def swing_mode(self) -> str | None:
        both = (int(bool(self._values.get(AC_SWING_V))), int(bool(self._values.get(AC_SWING_H))))
        return next((name for name, pair in SWINGS.items() if pair == both), "off")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.send({POW: 0})
        else:
            await self.coordinator.send({POW: 1, MOD: AC_MODES[hvac_mode.value]})

    async def async_turn_on(self) -> None:
        await self.coordinator.send({POW: 1})

    async def async_turn_off(self) -> None:
        await self.coordinator.send({POW: 0})

    async def async_set_temperature(self, **kwargs: Any) -> None:
        values: dict[str, Any] = {}
        if (mode := kwargs.get("hvac_mode")) is not None:
            values.update({POW: 0} if mode == HVACMode.OFF else {POW: 1, MOD: AC_MODES[HVACMode(mode).value]})
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            values[AC_SET] = round(temperature)
        if values:
            await self.coordinator.send(values)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.coordinator.send({AC_FAN: AC_FANS[fan_mode]})

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        vertical, horizontal = SWINGS[swing_mode]
        values = {AC_SWING_V: vertical}
        if AC_SWING_H in self._values:
            values[AC_SWING_H] = horizontal
        await self.coordinator.send(values)
