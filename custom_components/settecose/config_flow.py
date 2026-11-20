"""Einrichtung: Adresse und persönliches Token (Settecose › Mehr › Home Assistant)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SettecoseApi, SettecoseAuthError, SettecoseError
from .const import (
    CONF_PRESENCE,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_URL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_URL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)


class SettecoseConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _check(self, url: str, token: str) -> tuple[dict[str, Any] | None, str | None, str | None]:
        api = SettecoseApi(async_get_clientsession(self.hass), url, token)
        try:
            me = await api.me()
        except SettecoseAuthError:
            return None, None, "invalid_auth"
        except SettecoseError:
            return None, None, "cannot_connect"
        return me, api.space_id, None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].strip().rstrip("/")
            token = user_input[CONF_TOKEN].strip()
            me, space_id, error = await self._check(url, token)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(space_id)
                self._abort_if_unique_id_configured()
                space = next((s for s in me["spaces"] if s["id"] == space_id), {"name": "Settecose"})
                return self.async_create_entry(
                    title=f"Settecose {space['name']}", data={CONF_URL: url, CONF_TOKEN: token}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_URL, default=(user_input or {}).get(CONF_URL, DEFAULT_URL)): str,
                    vol.Required(CONF_TOKEN): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            _, space_id, error = await self._check(entry.data[CONF_URL], user_input[CONF_TOKEN].strip())
            if error:
                errors["base"] = error
            elif space_id != entry.unique_id:
                errors["base"] = "other_space"
            else:
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_TOKEN: user_input[CONF_TOKEN].strip()}
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SettecoseOptionsFlow()


class SettecoseOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=3600)),
                    vol.Required(CONF_PRESENCE, default=options.get(CONF_PRESENCE, True)): bool,
                }
            ),
        )
