"""Adding the Gree+ account."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ewpe_hp.cloud import password_hash
from custom_components.ewpe_hp.const import DOMAIN

from .fake import EMAIL, PASSWORD, UID, Broker, Cloud, Versati

FORM = {"region": "europe", "username": EMAIL, "password": PASSWORD}


async def test_account_is_added_without_its_password(hass: HomeAssistant, cloud: Cloud, broker: Broker) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == EMAIL
    assert result["data"] == {"region": "europe", "username": EMAIL, "password_hash": password_hash(PASSWORD)}
    assert PASSWORD not in str(result["data"])
    assert result["result"].unique_id == f"europe_{UID}"


async def test_wrong_password(hass: HomeAssistant, cloud: Cloud) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**FORM, "password": "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cloud_down(hass: HomeAssistant, cloud: Cloud) -> None:
    cloud.down = True
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_account_without_units(hass: HomeAssistant, cloud: Cloud, unit: Versati, monkeypatch) -> None:
    monkeypatch.setattr(cloud, "handle", _without_units(cloud.handle))
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["errors"] == {"base": "no_units"}


def _without_units(handle):
    def without(path, body):
        answer = handle(path, body)
        return {"r": 200, "home": []} if path == "/App/GetHomes" else answer

    return without


async def test_same_account_twice(hass: HomeAssistant, cloud: Cloud, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_sign_in_again(hass: HomeAssistant, cloud: Cloud, broker: Broker, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, data={**entry.data, "password_hash": "0" * 32})
    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"username": EMAIL, "password": "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"username": EMAIL, "password": PASSWORD})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password_hash"] == password_hash(PASSWORD)
    await hass.config_entries.async_unload(entry.entry_id)
