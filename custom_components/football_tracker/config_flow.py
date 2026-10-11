"""Config flow: search a team by name, pick it, done."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
)

from .api import EspnClient, EspnError
from .const import (
    CONF_BROADCASTS,
    CONF_HISTORY_YEARS,
    CONF_INCLUDE_FRIENDLIES,
    CONF_KICKOFF_NOTICE,
    CONF_TEAM_ID,
    CONF_TEAM_NAME,
    CONF_TEAM_QUERY,
    DEFAULT_BROADCASTS,
    DEFAULT_HISTORY_YEARS,
    DEFAULT_KICKOFF_NOTICE,
    DEFAULT_TEAM_QUERY,
    DOMAIN,
)


class FootballTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._teams: dict[str, str] = {}
        self._labels: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = EspnClient(async_get_clientsession(self.hass))
            try:
                teams = await client.search_teams(user_input[CONF_TEAM_QUERY])
            except EspnError:
                errors["base"] = "cannot_connect"
            else:
                if teams:
                    self._teams = {t["id"]: t["name"] for t in teams}
                    self._labels = {t["id"]: t["label"] for t in teams}
                    return await self.async_step_pick()
                errors[CONF_TEAM_QUERY] = "no_teams"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_TEAM_QUERY, default=DEFAULT_TEAM_QUERY): str}
            ),
            errors=errors,
        )

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            team_id = user_input[CONF_TEAM_ID]
            await self.async_set_unique_id(team_id)
            self._abort_if_unique_id_configured()
            name = self._teams[team_id]
            return self.async_create_entry(
                title=name, data={CONF_TEAM_ID: team_id, CONF_TEAM_NAME: name}
            )

        options = [SelectOptionDict(value=k, label=v) for k, v in self._labels.items()]
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TEAM_ID, default=options[0]["value"]): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return FootballTrackerOptionsFlow()


class FootballTrackerOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        opts = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BROADCASTS, default=opts.get(CONF_BROADCASTS, DEFAULT_BROADCASTS)
                    ): TextSelector(TextSelectorConfig(multiline=True)),
                    vol.Required(
                        CONF_KICKOFF_NOTICE,
                        default=opts.get(CONF_KICKOFF_NOTICE, DEFAULT_KICKOFF_NOTICE),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=5, max=240, step=5, unit_of_measurement="min",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_INCLUDE_FRIENDLIES,
                        default=opts.get(CONF_INCLUDE_FRIENDLIES, False),
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_HISTORY_YEARS,
    CONF_INCLUDE_FRIENDLIES,
                        default=opts.get(CONF_HISTORY_YEARS, DEFAULT_HISTORY_YEARS),
                    ): NumberSelector(
                        NumberSelectorConfig(min=1, max=5, step=1, mode=NumberSelectorMode.SLIDER)
                    ),
                }
            ),
        )
