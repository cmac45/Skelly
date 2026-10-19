"""sensor.skelly_tools: the tools Skelly has right now, for the dashboard.

Built by the same code that hands Skelly his tools each turn (current_toolbox),
so it can't drift from what he can actually do. It changes with the
personality dropdown, sunrise and sunset, the curtain scene catalog, and a
deploy-personas reload.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import (
    CATALOG_SENSOR,
    PERSONALITY_SELECT,
    SIGNAL_PERSONAS_RELOADED,
    SONGS,
    SOUNDS,
    _pick,
    current_toolbox,
    personality_tools,
)

# How each tool reads on the dashboard.
LABELS = {
    "set_yard_mood": "Light moods",
    "play_curtain_scene": "Curtain scenes",
    "show_workato": "Workato logo",
    "play_sound": "Sound effects",
    "play_song": "Songs",
    "stop_song": "Stop music",
}


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Add the one sensor (loaded by skelly_tools itself)."""
    async_add_entities([SkellyToolsSensor()])


class SkellyToolsSensor(SensorEntity):
    """How many tools Skelly has, with their names as attributes."""

    _attr_name = "Skelly tools"
    _attr_unique_id = "skelly_tools_active"
    _attr_icon = "mdi:toolbox"
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "tools"

    async def async_added_to_hass(self) -> None:
        """Recompute whenever something that decides the toolbox changes."""

        @callback
        def refresh(_event: Event | None = None) -> None:
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [PERSONALITY_SELECT, "sun.sun", CATALOG_SENSOR], refresh
            )
        )
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_PERSONAS_RELOADED, refresh))

    @property
    def native_value(self) -> int:
        return len(current_toolbox(self.hass)[0])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tools = [tool.name for tool in current_toolbox(self.hass)[0]]
        choices = personality_tools(self.hass)
        state = self.hass.states.get(PERSONALITY_SELECT)
        return {
            "personality": state.state if state else None,
            "tools": [LABELS.get(name, name) for name in tools],
            "tool_ids": tools,
            "sounds": _pick(choices.get("sounds"), SOUNDS) if "play_sound" in tools else [],
            "songs": _pick(choices.get("songs"), SONGS) if "play_song" in tools else [],
            "lights": "on" if "set_yard_mood" in tools else "after dark",
        }
