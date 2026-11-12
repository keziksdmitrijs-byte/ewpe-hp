"""EWPE HP: GREE Versati heat pumps in Home Assistant through the Gree+ (EWPE) cloud."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.const import CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .cloud import AuthError, Cloud, CloudError
from .const import CONF_PASSWORD_HASH, CONF_REGION, DEFAULT_REGION, REGIONS
from .coordinator import Account, EwpeConfigEntry, UnitCoordinator
from .link import GatewayLink, MqttLink

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]


async def async_setup_entry(hass: HomeAssistant, entry: EwpeConfigEntry) -> bool:
    api, broker = REGIONS.get(entry.data[CONF_REGION], REGIONS[DEFAULT_REGION])
    cloud = Cloud(async_get_clientsession(hass), api, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD_HASH])
    try:
        await cloud.login()
        units = await cloud.units()
    except AuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except CloudError as err:
        raise ConfigEntryNotReady(str(err)) from err

    account = Account(cloud=cloud, mqtt=MqttLink(cloud, broker), gateway=GatewayLink(cloud))
    entry.runtime_data = account
    account.mqtt.start()
    entry.async_on_unload(account.mqtt.stop)

    for unit in units:
        coordinator = UnitCoordinator(hass, entry, account, unit)
        await account.mqtt.add(unit, coordinator.reported)
        account.units.append(coordinator)

    # a unit that is offline now must not keep the others out
    results = await asyncio.gather(*(coordinator.async_refresh() for coordinator in account.units), return_exceptions=True)
    for coordinator, result in zip(account.units, results, strict=True):
        if isinstance(result, Exception):
            _LOGGER.warning("%s: %s", coordinator.unit.name, result)
    if account.units and all(coordinator.data is None for coordinator in account.units):
        if account.mqtt.auth_failed:
            raise ConfigEntryAuthFailed("The Gree+ account was refused")
        raise ConfigEntryNotReady("No unit of the account answered")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EwpeConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
