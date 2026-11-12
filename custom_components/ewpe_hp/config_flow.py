"""Signing in with the Gree+ account."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .cloud import AuthError, Cloud, CloudError, password_hash
from .const import CONF_PASSWORD_HASH, CONF_REGION, DEFAULT_REGION, DOMAIN, REGIONS


def _schema(region: str = DEFAULT_REGION, username: str = "") -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_REGION, default=region): SelectSelector(
                SelectSelectorConfig(options=list(REGIONS), translation_key=CONF_REGION, mode=SelectSelectorMode.DROPDOWN)
            ),
            vol.Required(CONF_USERNAME, default=username): TextSelector(
                TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
            ),
            vol.Required(CONF_PASSWORD): TextSelector(
                TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
            ),
        }
    )


class EwpeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _sign_in(self, user_input: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str], Cloud | None]:
        username = user_input[CONF_USERNAME].strip()
        data = {
            CONF_REGION: user_input[CONF_REGION],
            CONF_USERNAME: username,
            CONF_PASSWORD_HASH: password_hash(user_input[CONF_PASSWORD]),
        }
        cloud = Cloud(async_get_clientsession(self.hass), REGIONS[data[CONF_REGION]][0], username, data[CONF_PASSWORD_HASH])
        try:
            await cloud.login()
            units = await cloud.units()
        except AuthError:
            return data, {"base": "invalid_auth"}, None
        except CloudError:
            return data, {"base": "cannot_connect"}, None
        if not units:
            return data, {"base": "no_units"}, None
        return data, {}, cloud

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors, cloud = await self._sign_in(user_input)
            if cloud is not None:
                await self.async_set_unique_id(f"{data[CONF_REGION]}_{cloud.uid}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_USERNAME], data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=_schema((user_input or {}).get(CONF_REGION, DEFAULT_REGION), (user_input or {}).get(CONF_USERNAME, "")),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors, cloud = await self._sign_in({**user_input, CONF_REGION: entry.data[CONF_REGION]})
            if cloud is not None:
                await self.async_set_unique_id(f"{data[CONF_REGION]}_{cloud.uid}")
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="username")
                    ),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
                    ),
                }
            ),
            errors=errors,
        )
