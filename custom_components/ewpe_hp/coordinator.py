"""One coordinator per unit: polls it through the cloud and sends it commands."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .cloud import AuthError, Cloud, CloudError, CloudUnit
from .const import (
    AC_COLUMNS,
    AIR_CONDITIONER,
    COLUMNS,
    COLUMNS_PER_REQUEST,
    DOMAIN,
    HEAT_PUMP,
    HEAT_WATER_SET,
    NOT_FITTED,
    PROBE,
    SCAN_INTERVAL_SECONDS,
    TEMPERATURE_OFFSET,
)
from .link import GatewayLink, LinkError, MqttLink, over_mqtt, values_of

_LOGGER = logging.getLogger(__name__)


@dataclass
class Account:
    cloud: Cloud
    mqtt: MqttLink
    gateway: GatewayLink
    units: list[UnitCoordinator] = field(default_factory=list)


type EwpeConfigEntry = ConfigEntry[Account]


def temperature(values: dict[str, Any], name: str) -> float | None:
    """<name>Hi is whole degrees + 100, <name>Lo tenths; -30.0 means no sensor is fitted."""
    high, low = values.get(f"{name}Hi"), values.get(f"{name}Lo")
    if not isinstance(high, int) or not isinstance(low, int):
        return None
    value = round(high - TEMPERATURE_OFFSET + low / 10, 1)
    return None if value == NOT_FITTED else value


class UnitCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """The values of one unit, by Gree parameter name."""

    def __init__(self, hass: HomeAssistant, entry: EwpeConfigEntry, account: Account, unit: CloudUnit) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {unit.name}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
            always_update=False,
        )
        self.unit = unit
        self._account = account
        self.mqtt = over_mqtt(unit)
        self._proven = False
        # heat pump or air conditioner, from the unit's first answer
        self.kind: str | None = None
        # parameters this unit has never answered for are not asked again
        self._columns: list[str] = []

    @property
    def _link(self) -> MqttLink | GatewayLink:
        return self._account.mqtt if self.mqtt else self._account.gateway

    @callback
    def reported(self, values: dict[str, Any]) -> None:
        """A change the unit reported by itself."""
        if self.data is not None:
            self.async_set_updated_data({**self.data, **values})

    async def _ask(self, message: dict[str, Any]) -> dict[str, Any]:
        """One pack to the unit. Until it has answered once, the other link is tried when the first stays silent."""
        try:
            answer = await self._link.request(self.unit, message)
        except LinkError:
            if self._proven:
                raise
            self.mqtt = not self.mqtt
            try:
                answer = await self._link.request(self.unit, message)
            except LinkError:
                self.mqtt = not self.mqtt
                raise
            _LOGGER.info("%s answers over %s", self.unit.name, "MQTT" if self.mqtt else "its gateway")
        self._proven = True
        return answer

    async def _async_update_data(self) -> dict[str, Any]:
        if self._account.mqtt.auth_failed:
            raise ConfigEntryAuthFailed("The Gree+ account was refused")
        values: dict[str, Any] = {}
        answered = False
        try:
            if self.kind is None:
                self.kind = await self._probe()
                self._columns = list(COLUMNS if self.kind == HEAT_PUMP else AC_COLUMNS)
            for start in range(0, len(self._columns), COLUMNS_PER_REQUEST):
                part = self._columns[start : start + COLUMNS_PER_REQUEST]
                answer = await self._ask({"t": "status", "cols": part})
                if answer.get("t") == "dat":
                    answered = True
                    values.update(values_of(answer))
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (LinkError, CloudError) as err:
            raise UpdateFailed(str(err)) from err
        if not answered:
            raise UpdateFailed(f"{self.unit.name} answered without data")
        if self.data is None:
            missing = [name for name in self._columns if name not in values]
            if missing:
                _LOGGER.debug("%s does not report %s", self.unit.name, missing)
                self._columns = [name for name in self._columns if name in values]
        return values

    async def _probe(self) -> str:
        """A Versati answers with its heating water set point (20-60 °C), an air conditioner with a room one."""
        answer = await self._ask({"t": "status", "cols": list(PROBE)})
        if answer.get("t") != "dat":
            raise UpdateFailed(f"{self.unit.name} answered without data")
        values = values_of(answer)
        water = values.get(HEAT_WATER_SET)
        kind = HEAT_PUMP if isinstance(water, int) and water >= 5 else AIR_CONDITIONER if "SetTem" in values else HEAT_PUMP
        _LOGGER.debug("%s is a %s", self.unit.name, kind)
        return kind

    async def send(self, values: dict[str, Any]) -> None:
        """Sets parameters on the unit; what it has taken shows straight away."""
        message = {"t": "cmd", "opt": list(values), "p": list(values.values())}
        try:
            answer = await self._ask(message)
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except (LinkError, CloudError) as err:
            raise HomeAssistantError(f"{self.unit.name}: {err}") from err
        if answer.get("r", 200) != 200:
            raise HomeAssistantError(f"{self.unit.name} refused {', '.join(values)} (code {answer.get('r')})")
        taken = values_of(answer) or values
        self.async_set_updated_data({**(self.data or {}), **taken})
        await self.async_request_refresh()
