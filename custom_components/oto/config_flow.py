"""Config flow for OTO."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OtoApiClient, OtoAuthError, OtoConnectionError, OtoError
from .const import (
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_UID,
    CONF_WATERING_DEPTH,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WATERING_DEPTH_MM,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MAX_WATERING_DEPTH_MM,
    MIN_SCAN_INTERVAL,
    MIN_WATERING_DEPTH_MM,
)


class OtoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an OTO config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip().lower()
            try:
                client = OtoApiClient(async_get_clientsession(self.hass))
                credentials = await client.async_login(email, user_input[CONF_PASSWORD])
                devices = await client.async_get_devices()
            except OtoAuthError:
                errors["base"] = "invalid_auth"
            except OtoConnectionError:
                errors["base"] = "cannot_connect"
            except OtoError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(credentials.uid)
                self._abort_if_unique_id_configured()
                title = devices[0].name if len(devices) == 1 else "OTO"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_EMAIL: email,
                        CONF_UID: credentials.uid,
                        CONF_REFRESH_TOKEN: credentials.refresh_token,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Start reauthentication."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Complete reauthentication."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                client = OtoApiClient(async_get_clientsession(self.hass))
                credentials = await client.async_login(
                    self._reauth_entry.data[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
                await client.async_get_devices()
            except OtoAuthError:
                errors["base"] = "invalid_auth"
            except OtoConnectionError:
                errors["base"] = "cannot_connect"
            except OtoError:
                errors["base"] = "unknown"
            else:
                if credentials.uid != self._reauth_entry.data[CONF_UID]:
                    errors["base"] = "wrong_account"
                    return self.async_show_form(
                        step_id="reauth_confirm",
                        data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
                        errors=errors,
                    )
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data_updates={
                        CONF_UID: credentials.uid,
                        CONF_REFRESH_TOKEN: credentials.refresh_token,
                    },
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OtoOptionsFlow:
        """Return the options flow."""
        return OtoOptionsFlow()


class OtoOptionsFlow(config_entries.OptionsFlow):
    """Handle OTO options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_WATERING_DEPTH,
                        default=self.config_entry.options.get(
                            CONF_WATERING_DEPTH, DEFAULT_WATERING_DEPTH_MM
                        ),
                    ): vol.All(
                        vol.Coerce(float),
                        vol.Range(min=MIN_WATERING_DEPTH_MM, max=MAX_WATERING_DEPTH_MM),
                    ),
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                    ),
                }
            ),
        )
