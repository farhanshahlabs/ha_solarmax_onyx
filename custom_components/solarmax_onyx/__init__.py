"""CloudInverter integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant

from .api import CloudInverterAPI
from .const import DOMAIN, CONF_MEMBER_ID, CONF_GOODS_ID, CONF_GROUP_ID
from .coordinator import CloudInverterCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = CloudInverterAPI(
        member_id=entry.data[CONF_MEMBER_ID],
        password=entry.data[CONF_PASSWORD],
    )
    coordinator = CloudInverterCoordinator(
        hass, api,
        goods_id=entry.data[CONF_GOODS_ID],
        group_id=entry.data.get(CONF_GROUP_ID, ""),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
