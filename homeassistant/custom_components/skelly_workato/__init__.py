"""Skelly via Workato: a conversation agent that talks to Workato's AI Gateway.

Workato's AI Gateway speaks the OpenAI chat-completions format and forwards to
Claude; HA has no built-in integration that can point at it, so this is one.
Requests go straight to ai.workato.com. Replies are streamed, so the voice
pipeline starts speaking on the first words.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant

PLATFORMS = [Platform.CONVERSATION]

type WorkatoConfigEntry = ConfigEntry[str]


async def async_setup_entry(hass: HomeAssistant, entry: WorkatoConfigEntry) -> bool:
    """Set up the Workato key and its conversation agents."""
    entry.runtime_data = entry.data[CONF_API_KEY]
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: WorkatoConfigEntry) -> None:
    """Reload when an agent is added or reconfigured."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: WorkatoConfigEntry) -> bool:
    """Unload the agents."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
