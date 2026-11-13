"""The unit in Home Assistant: what it shows, what it takes, and how it is reached."""

from __future__ import annotations

import asyncio
import base64
import json

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import get_diagnostics_for_config_entry

from custom_components.ewpe_hp.crypto import decrypt, encrypt, open_pack, seal

from .fake import EMAIL, KEY, MAC, Broker, Cloud, Versati

DEVICE = "versati_iv"


def test_packs_round_trip_and_junk_padding_is_dropped() -> None:
    message = {"t": "status", "cols": ["Pow", "Mod"]}
    assert open_pack(KEY, seal(KEY, message)) == message
    # a module that pads with spaces instead of PKCS#7
    text = json.dumps(message).encode()
    padded = text + b" " * (16 - len(text) % 16)
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    raw = Cipher(algorithms.AES(KEY.encode()), modes.ECB()).encryptor().update(padded)
    assert open_pack(KEY, base64.b64encode(raw).decode()) == message
    assert decrypt(b"k" * 16, encrypt(b"k" * 16, b"x" * 16)) == b"x" * 16


async def test_values_show(hass: HomeAssistant, loaded: MockConfigEntry, unit: Versati) -> None:
    assert loaded.state is ConfigEntryState.LOADED
    assert hass.states.get(f"switch.{DEVICE}_power").state == STATE_ON
    assert hass.states.get(f"select.{DEVICE}_mode").state == "heat_hot_water"
    assert hass.states.get(f"select.{DEVICE}_heat_hot_water_priority").state == "hot_water"
    assert float(hass.states.get(f"number.{DEVICE}_heating_water_setpoint").state) == 35
    tank = hass.states.get(f"water_heater.{DEVICE}_hot_water_tank")
    assert tank.attributes["temperature"] == 48
    assert tank.attributes["current_temperature"] == 46.3
    assert tank.state == "heat_pump"
    assert float(hass.states.get(f"sensor.{DEVICE}_water_outlet").state) == 34.5
    assert float(hass.states.get(f"sensor.{DEVICE}_water_inlet").state) == 30.7
    assert hass.states.get(f"sensor.{DEVICE}_error_code").state == "0"
    assert hass.states.get(f"binary_sensor.{DEVICE}_error").state == STATE_OFF
    # the room sensor is not fitted (-30 °C): no entity for it
    assert hass.states.get(f"sensor.{DEVICE}_room_temperature") is None
    device = er.async_get(hass).async_get(f"switch.{DEVICE}_power")
    assert device.unique_id == f"{MAC}_power"
    # status goes in parts, never more than 12 parameters at a time
    assert all(len(cols) <= 12 for cols in unit.status_requests)


async def test_settings_are_sent(hass: HomeAssistant, loaded: MockConfigEntry, unit: Versati) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": f"select.{DEVICE}_mode", "option": "heat"}, blocking=True
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": f"number.{DEVICE}_heating_water_setpoint", "value": 41}, blocking=True
    )
    await hass.services.async_call(
        "water_heater",
        "set_temperature",
        {"entity_id": f"water_heater.{DEVICE}_hot_water_tank", "temperature": 52},
        blocking=True,
    )
    await hass.services.async_call("switch", "turn_off", {"entity_id": f"switch.{DEVICE}_power"}, blocking=True)
    assert unit.commands == [{"Mod": 1}, {"HeWatOutTemSet": 41}, {"WatBoxTemSet": 52}, {"Pow": 0}]
    assert hass.states.get(f"select.{DEVICE}_mode").state == "heat"
    assert hass.states.get(f"water_heater.{DEVICE}_hot_water_tank").attributes["temperature"] == 52
    assert hass.states.get(f"switch.{DEVICE}_power").state == STATE_OFF


async def test_a_refused_setting_says_so(hass: HomeAssistant, loaded: MockConfigEntry, unit: Versati) -> None:
    unit.refuse = {"Mod"}
    with pytest.raises(HomeAssistantError, match="refused"):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": f"select.{DEVICE}_mode", "option": "cool"}, blocking=True
        )
    assert hass.states.get(f"select.{DEVICE}_mode").state == "heat_hot_water"


async def test_changes_the_unit_reports_show_at_once(hass: HomeAssistant, loaded: MockConfigEntry, broker: Broker) -> None:
    broker.report({"Pow": 0, "WatBoxTemHi": 150, "WatBoxTemLo": 1})
    await hass.async_block_till_done()
    assert hass.states.get(f"switch.{DEVICE}_power").state == STATE_OFF
    assert hass.states.get(f"water_heater.{DEVICE}_hot_water_tank").attributes["current_temperature"] == 50.1


async def test_an_offline_unit_goes_unavailable_and_comes_back(
    hass: HomeAssistant, loaded: MockConfigEntry, unit: Versati
) -> None:
    coordinator = loaded.runtime_data.units[0]
    unit.online = False
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"switch.{DEVICE}_power").state == STATE_UNAVAILABLE
    unit.online = True
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"switch.{DEVICE}_power").state == STATE_ON


async def test_older_module_goes_through_its_gateway(
    hass: HomeAssistant, entry: MockConfigEntry, broker: Broker, gateway: Cloud, unit: Versati
) -> None:
    unit.version = "V2.0.0"
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert not entry.runtime_data.units[0].mqtt
    assert hass.states.get(f"select.{DEVICE}_mode").state == "heat_hot_water"
    await hass.services.async_call("switch", "turn_on", {"entity_id": f"switch.{DEVICE}_quiet"}, blocking=True)
    assert unit.commands == [{"Quiet": 1}]
    await hass.config_entries.async_unload(entry.entry_id)


async def test_a_silent_unit_is_tried_through_its_gateway(
    hass: HomeAssistant, entry: MockConfigEntry, broker: Broker, gateway: Cloud
) -> None:
    broker.silent = True
    entry.add_to_hass(hass)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("custom_components.ewpe_hp.link.REQUEST_TIMEOUT", 0.2)
        patch.setattr("custom_components.ewpe_hp.link.MQTT_TIMEOUT", 0.2)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert not entry.runtime_data.units[0].mqtt
    assert hass.states.get(f"switch.{DEVICE}_power").state == STATE_ON
    await hass.config_entries.async_unload(entry.entry_id)


async def test_an_expired_token_is_renewed(hass: HomeAssistant, loaded: MockConfigEntry, cloud: Cloud, broker: Broker) -> None:
    logins = cloud.logins
    cloud.token = "token-2"
    assert len(await loaded.runtime_data.cloud.units()) == 1
    assert cloud.logins == logins + 1


async def test_a_refused_account_asks_to_sign_in_again(
    hass: HomeAssistant, entry: MockConfigEntry, cloud: Cloud, broker: Broker
) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, data={**entry.data, "password_hash": "0" * 32})
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_cloud_down_retries_later(hass: HomeAssistant, entry: MockConfigEntry, cloud: Cloud, broker: Broker) -> None:
    cloud.down = True
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_diagnostics_keep_secrets_out(hass: HomeAssistant, hass_client, loaded: MockConfigEntry) -> None:
    result = await get_diagnostics_for_config_entry(hass, hass_client, loaded)
    text = json.dumps(result)
    assert KEY not in text and EMAIL not in text and loaded.data["password_hash"] not in text
    assert result["units"][0]["values"]["Mod"] == 4
    assert result["units"][0]["link"] == "mqtt"


async def test_mqtt_session_uses_the_account(loaded: MockConfigEntry, broker: Broker) -> None:
    await asyncio.sleep(0)
    settings = broker.connections[0]
    assert settings["hostname"] == "mqtt-eu.gree.com" and settings["port"] == 1984
    assert settings["username"] == "4242" and settings["password"] == "token-1"
    assert broker.clients[0].subscriptions == [f"response/{MAC}/#", f"status/{MAC}/#", f"connect/{MAC}"]
