"""Fixtures: the fake Gree+ cloud, its broker and the unit, wired into Home Assistant."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ewpe_hp.cloud import password_hash
from custom_components.ewpe_hp.const import CONF_PASSWORD_HASH, CONF_REGION, DOMAIN

from .fake import EMAIL, PASSWORD, UID, Broker, Cloud, Versati, gateway_server


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def unit() -> Versati:
    return Versati()


@pytest.fixture
def cloud(unit: Versati, aioclient_mock) -> Cloud:
    fake = Cloud(unit)
    aioclient_mock.post(re.compile(r"https://eugrih\.gree\.com/App/.*"), side_effect=fake.side_effect)
    return fake


@pytest.fixture
def broker(cloud: Cloud) -> AsyncGenerator[Broker]:
    fake = Broker(cloud)
    with patch("custom_components.ewpe_hp.link.aiomqtt.Client", fake):
        yield fake


@pytest.fixture
async def gateway(cloud: Cloud, socket_enabled) -> AsyncGenerator[Cloud]:
    server = await gateway_server(cloud)
    yield cloud
    server.close()
    await server.wait_closed()


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=EMAIL,
        unique_id=f"europe_{UID}",
        data={CONF_REGION: "europe", CONF_USERNAME: EMAIL, CONF_PASSWORD_HASH: password_hash(PASSWORD)},
    )


@pytest.fixture
async def loaded(hass: HomeAssistant, entry: MockConfigEntry, broker: Broker) -> AsyncGenerator[MockConfigEntry]:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
