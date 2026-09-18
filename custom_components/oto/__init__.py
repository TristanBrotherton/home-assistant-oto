"""The unofficial OTO integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OtoApiClient, OtoCredentials
from .const import (
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_UID,
    DEFAULT_SCAN_INTERVAL,
    PLATFORMS,
)
from .coordinator import OtoCoordinator

OtoConfigEntry = ConfigEntry[OtoCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: OtoConfigEntry) -> bool:
    """Set up OTO from a config entry."""

    async def async_token_updated(credentials: OtoCredentials) -> None:
        if credentials.refresh_token != entry.data.get(
            CONF_REFRESH_TOKEN
        ) or credentials.uid != entry.data.get(CONF_UID):
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_REFRESH_TOKEN: credentials.refresh_token,
                    CONF_UID: credentials.uid,
                },
            )

    client = OtoApiClient(
        async_get_clientsession(hass),
        OtoCredentials(
            uid=entry.data[CONF_UID],
            refresh_token=entry.data[CONF_REFRESH_TOKEN],
        ),
        async_token_updated,
    )
    scan_interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
    coordinator = OtoCoordinator(
        hass,
        entry,
        client,
        timedelta(seconds=scan_interval),
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OtoConfigEntry) -> bool:
    """Unload an OTO config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: OtoConfigEntry) -> None:
    """Reload after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entries."""
    return True
