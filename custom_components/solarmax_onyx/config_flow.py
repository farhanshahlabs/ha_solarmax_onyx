"""Config flow for CloudInverter integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .api import CloudInverterAPI, CloudInverterAuthError, CloudInverterApiError
from .const import DOMAIN, CONF_MEMBER_ID, CONF_GOODS_ID, CONF_GROUP_ID, CONF_PLANT_NAME

_LOGGER = logging.getLogger(__name__)


class CloudInverterConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the CloudInverter config flow.

    Each config entry represents one plant. Users can add the integration
    multiple times to monitor multiple plants from the same account.
    """

    VERSION = 1

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""
        self._plants: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            api = CloudInverterAPI(self._username, self._password)
            try:
                async with aiohttp.ClientSession() as session:
                    await api.async_login(session)
                    self._plants = await api.async_get_plants(session)
            except CloudInverterAuthError:
                errors["base"] = "invalid_auth"
            except CloudInverterApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"

            if not errors:
                if len(self._plants) == 1:
                    return self._create_entry(self._plants[0])
                return await self.async_step_plant()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

    async def async_step_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            group_id = user_input[CONF_GROUP_ID]
            plant = next(p for p in self._plants if p["group_id"] == group_id)
            return self._create_entry(plant)

        # Filter out plants already configured
        configured = {
            entry.data[CONF_GROUP_ID]
            for entry in self._async_current_entries()
        }
        available = [p for p in self._plants if p["group_id"] not in configured]

        if not available:
            return self.async_abort(reason="all_plants_configured")

        plant_options = {p["group_id"]: p["plant_name"] for p in available}
        return self.async_show_form(
            step_id="plant",
            data_schema=vol.Schema({
                vol.Required(CONF_GROUP_ID): vol.In(plant_options)
            }),
        )

    def _create_entry(self, plant: dict) -> ConfigFlowResult:
        self._async_abort_entries_match({CONF_GROUP_ID: plant["group_id"]})
        return self.async_create_entry(
            title=plant["plant_name"],
            data={
                CONF_MEMBER_ID:  self._username,
                CONF_PASSWORD:   self._password,
                CONF_GROUP_ID:   plant["group_id"],
                CONF_GOODS_ID:   plant["goods_id"],
                CONF_PLANT_NAME: plant["plant_name"],
                "model":         plant.get("model", ""),
            },
        )
