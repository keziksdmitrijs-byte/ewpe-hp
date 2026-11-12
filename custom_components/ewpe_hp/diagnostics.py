"""Diagnostics: units and their values, never the account, its token or the units' keys."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD_HASH
from .coordinator import EwpeConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: EwpeConfigEntry) -> dict[str, Any]:
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_USERNAME, CONF_PASSWORD_HASH}),
        "mqtt_auth_failed": entry.runtime_data.mqtt.auth_failed,
        "units": [
            {
                **coordinator.unit.summary(),
                "link": "mqtt" if coordinator.mqtt else "gateway",
                "values": coordinator.data,
            }
            for coordinator in entry.runtime_data.units
        ],
    }
