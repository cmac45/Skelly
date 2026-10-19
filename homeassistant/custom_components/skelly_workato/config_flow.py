"""Config flow for Skelly via Workato: one API key, then conversation agents."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import (
    SOURCE_USER,
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY, CONF_MODEL, CONF_PROMPT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, TemplateSelector

from .const import BASE_URL, CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS, DEFAULT_MODEL, DOMAIN, LOGGER


class WorkatoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Workato AI Gateway key."""

    VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Each conversation agent is a subentry, like the Anthropic integration's."""
        return {"conversation": ConversationFlowHandler}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the key and check it with a one-token request."""
        errors = {}
        if user_input is not None:
            self._async_abort_entries_match(user_input)
            try:
                async with async_get_clientsession(self.hass).post(
                    f"{BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {user_input[CONF_API_KEY]}"},
                    json={
                        "model": DEFAULT_MODEL,
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "Hi"}],
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status in (401, 403):
                        errors["base"] = "invalid_auth"
                    elif resp.status != 200:
                        LOGGER.error("Workato key check failed: %s %s", resp.status, await resp.text())
                        errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            if not errors:
                return self.async_create_entry(title="Workato AI Gateway", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )


class ConversationFlowHandler(ConfigSubentryFlow):
    """Add or reconfigure a conversation agent. There is no LLM API choice: it is always skelly_tools."""

    def __init__(self) -> None:
        """Initialize the subentry flow."""
        self.options: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Create a new agent."""
        self.options = {CONF_MODEL: DEFAULT_MODEL, CONF_MAX_TOKENS: DEFAULT_MAX_TOKENS}
        return await self.async_step_init(user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Change an existing agent (tools/skelly.py set-prompt uses this)."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_init(user_input)

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Show or save the agent's settings."""
        if self._get_entry().state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="entry_not_loaded")

        if user_input is not None:
            user_input[CONF_MAX_TOKENS] = int(user_input[CONF_MAX_TOKENS])
            if self.source == SOURCE_USER:
                return self.async_create_entry(title="Skelly (Workato)", data=user_input)
            return self.async_update_and_abort(
                self._get_entry(), self._get_reconfigure_subentry(), data=user_input
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODEL, default=self.options.get(CONF_MODEL, DEFAULT_MODEL)): str,
                    vol.Optional(
                        CONF_PROMPT, description={"suggested_value": self.options.get(CONF_PROMPT, "")}
                    ): TemplateSelector(),
                    vol.Required(
                        CONF_MAX_TOKENS, default=self.options.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS)
                    ): NumberSelector(NumberSelectorConfig(min=50, max=1000, step=10)),
                }
            ),
        )
