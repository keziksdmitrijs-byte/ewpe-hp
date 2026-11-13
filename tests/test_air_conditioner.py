"""A GREE air conditioner on the same Gree+ account as the Versati."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .fake import AC_MAC, AirCon, Broker, Cloud

AC = "climate.office_ac"


@pytest.fixture
def aircon(cloud: Cloud) -> AirCon:
    unit = AirCon()
    cloud.units.append(unit)
    return unit


@pytest.fixture
async def both(hass: HomeAssistant, entry: MockConfigEntry, broker: Broker, aircon: AirCon) -> AsyncGenerator[MockConfigEntry]:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_air_conditioner_shows_as_climate(hass: HomeAssistant, both: MockConfigEntry) -> None:
    state = hass.states.get(AC)
    assert state.state == "cool"
    assert state.attributes["current_temperature"] == 26
    assert state.attributes["temperature"] == 24
    assert state.attributes["fan_mode"] == "auto"
    assert state.attributes["swing_mode"] == "off"
    assert set(state.attributes["hvac_modes"]) == {"off", "auto", "cool", "dry", "fan_only", "heat"}
    # named as the Gree integration names them, so the NSPanel card finds them
    for key in ("quiet_mode", "xtra_fan", "fresh_air", "panel_light"):
        assert hass.states.get(f"switch.office_ac_{key}") is not None
    assert hass.states.get("switch.office_ac_panel_light").state == "on"
    # nothing of a heat pump for the air conditioner, nothing of an air conditioner for the Versati
    assert hass.states.get("select.office_ac_mode") is None
    assert hass.states.get("switch.office_ac_power") is None
    assert hass.states.get("climate.versati_iv") is None
    assert hass.states.get("select.versati_iv_mode").state == "heat_hot_water"
    assert er.async_get(hass).async_get(AC).unique_id == f"{AC_MAC}_air_conditioner"


async def test_air_conditioner_takes_commands(hass: HomeAssistant, both: MockConfigEntry, aircon: AirCon) -> None:
    await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": AC, "hvac_mode": "heat"}, blocking=True)
    await hass.services.async_call("climate", "set_temperature", {"entity_id": AC, "temperature": 21.6}, blocking=True)
    await hass.services.async_call("climate", "set_fan_mode", {"entity_id": AC, "fan_mode": "high"}, blocking=True)
    await hass.services.async_call("climate", "set_swing_mode", {"entity_id": AC, "swing_mode": "both"}, blocking=True)
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.office_ac_panel_light"}, blocking=True)
    await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": AC, "hvac_mode": "off"}, blocking=True)
    assert aircon.commands == [
        {"Pow": 1, "Mod": 4},
        {"SetTem": 22},
        {"WdSpd": 5},
        {"SwUpDn": 1, "SwingLfRig": 1},
        {"Lig": 0},
        {"Pow": 0},
    ]
    state = hass.states.get(AC)
    assert state.state == "off"
    assert state.attributes["temperature"] == 22
    assert state.attributes["fan_mode"] == "high"
    assert state.attributes["swing_mode"] == "both"
    await hass.services.async_call("climate", "turn_on", {"entity_id": AC}, blocking=True)
    assert hass.states.get(AC).state == "heat"
