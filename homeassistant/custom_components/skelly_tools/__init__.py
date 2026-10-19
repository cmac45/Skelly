"""Skelly's toolbox: the only tools the yard skeleton's voice assistant gets.

Registers an LLM API, "skelly_tools", with five tools: set_yard_mood (runs
script.skelly_mood), play_curtain_scene (plays a Govee curtain scene),
play_sound (a short effect on the ground speaker, media_player.skelly_music),
and play_song / stop_song (Skelly's Suno songs on that same speaker), plus
show_workato (the Workato colors and logo on the yard lights). Which of them he
gets depends on the "Skelly personality" dropdown: personas.json, written by
tools/skelly.py deploy-personas from homeassistant/personas/, lists each
personality's sounds, songs and extras.
Skelly's conversation agent is
given ONLY this API -- not the general Assist API. The Assist API would hand
him every entity exposed to Assist (the spa thermostat and jets, smart plugs,
deck lights...), and anyone on the driveway can talk to him. Through this API a
visitor can change the yard lights and play Skelly's sounds and songs, and
nothing else.
"""

from __future__ import annotations

import json
import pathlib

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, discovery, llm
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.json import JsonObjectType

DOMAIN = "skelly_tools"
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

MOODS = ["angry", "happy", "spooky", "scared", "sleepy", "party", "normal"]

PERSONALITY_SELECT = "input_select.skelly_personality"
PERSONAS_FILE = pathlib.Path(__file__).parent / "personas.json"
SIGNAL_PERSONAS_RELOADED = f"{DOMAIN}_personas_reloaded"

# Lights are a night-time effect: while the sun is up, Skelly gets no light tools
# at all (and LIGHTS_PROMPT is swapped for DAYLIGHT_PROMPT), so he can't switch the
# yard lights on in daylight. Sounds and songs work day and night.
LIGHTS_PROMPT = (
    "You are standing among the yard lights: the roofline, the big light "
    "curtains behind you and the spotlights around you. Use them like a stage "
    "effect, on your own initiative: when the conversation turns, change them to "
    "fit the moment with set_yard_mood (all the lights, a mood) or "
    "play_curtain_scene (one animated scene on the curtains). Never ask the "
    "visitor which color, mood or scene they want, and never offer choices. "
    "Change the lights when the mood shifts, not in every reply, and at most once "
    "per reply; curtain scenes take a few seconds to start. Never mention tools, "
    "settings or code, and never announce the change; just react in character. "
)
DAYLIGHT_PROMPT = (
    "It is daylight, so your yard lights stay dark until the sun goes down: you "
    "cannot change them right now. Don't promise light effects; if someone asks, "
    "tell them in character to come back after dark. Never mention tools, "
    "settings or code. "
)
SOUNDS_PROMPT = (
    "You also have play_sound: a short sound effect from the speaker at "
    "your feet, played while you talk (a wolf howl for a werewolf costume, an "
    "evil laugh when you win, a creaking door for a ghost story). Use it now and "
    "then for punch, at most once per reply and not in every reply; don't also "
    "say the sound out loud or describe it. "
)
SONGS_PROMPT = (
    "You have your own songs too: play_song when someone asks you to sing, rap, "
    "play music or start a dance party (shake_your_bones for little kids). Give "
    "it a one-sentence introduction and do NOT end with a question: you can't "
    "hear anyone over the music, so let the song play. stop_song if someone asks "
    "you to stop the music. "
)
NO_SONGS_PROMPT = "You have no songs to play right now; if asked, say so in character. "
NOTHING_ELSE_PROMPT = "You cannot control anything else at the house."

# The Workato demo personality's own words about Workato live in its profile
# (homeassistant/personas/workato_demo.yaml); this is only how to use the tool.
WORKATO_LIGHTS_PROMPT = (
    "When Workato comes up, use show_workato to put the Workato colors and logo "
    "on your lights. "
)


class ShowWorkatoTool(llm.Tool):
    """Put the Workato colors and logo on the yard lights."""

    name = "show_workato"
    description = (
        "Turn the lights around you to Workato's teal and blue and show the "
        "Workato logo on the big light curtains behind you, for about two minutes. "
        "Use it when someone mentions Workato or asks what powers you."
    )
    parameters = vol.Schema({})

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        """The workato mood in script.skelly_mood does the lights."""
        await hass.services.async_call(
            "script",
            "turn_on",
            {"entity_id": "script.skelly_mood", "variables": {"mood": "workato"}},
            blocking=True,
            context=llm_context.context,
        )
        return {"success": True, "note": "the logo appears on the curtains in a few seconds"}


class SetYardMoodTool(llm.Tool):
    """Set the yard lights to a mood for about a minute."""

    name = "set_yard_mood"
    description = (
        "Change all the lights around you (roofline, light curtains, spotlights) "
        "to match the mood of the conversation for about a minute, then they "
        "return to normal. Use it on your own when the mood shifts. "
        "angry = red and pulsing, happy = warm gold, spooky = purple and green, "
        "scared = a flicker then dim blue, sleepy = dim midnight blue, "
        "party = lively colors, normal = back to the usual look right away."
    )
    parameters = vol.Schema(
        {vol.Required("mood", description="The feeling to show"): vol.In(MOODS)}
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        """Start the mood script (it returns immediately; the mood runs ~1 min)."""
        mood = tool_input.tool_args["mood"]
        await hass.services.async_call(
            "script",
            "turn_on",
            {"entity_id": "script.skelly_mood", "variables": {"mood": mood}},
            blocking=True,
            context=llm_context.context,
        )
        return {"success": True, "mood": mood}


# Scenes held back from Skelly because their names suggest strobing or rapid
# flashing (photosensitivity; small children walk past). Chosen by NAME -- the
# animations were not inspected, so add any others that turn out to flash hard.
BLOCKED_SCENES = {"Siren", "Illusion", "Psychedelic Mushroom", "Beats", "Laser Tower", "Shoot"}

CATALOG_SENSOR = "sensor.govee_curtain_main_scenes"
CURTAIN_SELECT = "select.govee_curtain_main_scene"


def curtain_scene_names(hass: HomeAssistant) -> list[str]:
    """The lead curtain's built-in scenes, from the hourly catalog sensor."""
    state = hass.states.get(CATALOG_SENSOR)
    caps = (state.attributes.get("capabilities") if state else None) or []
    names: list[str] = []
    for cap in caps:
        for opt in (cap.get("parameters") or {}).get("options") or []:
            name = opt.get("name")
            if name and name not in BLOCKED_SCENES and name not in names:
                names.append(name)
    return names


class PlayCurtainSceneTool(llm.Tool):
    """Play one animated scene on the light curtains."""

    name = "play_curtain_scene"
    description = (
        "Play an animated scene on the big light curtains behind you, for "
        "example Witch, Graveyard, Bat, Demon, Fire Dragon, Skeleton Juggler or "
        "Dancing Pumpkin. Pick the scene that best fits the moment in the "
        "conversation (a costume, a story, a joke), on your own initiative. It "
        "starts after a few seconds and keeps playing."
    )

    def __init__(self, names: list[str]) -> None:
        """Offer exactly the scenes in the current catalog."""
        self.parameters = vol.Schema(
            {vol.Required("scene", description="Scene name, exactly as listed"): vol.In(names)}
        )

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        """Play it through the existing curtain scene dropdown (same path as the dashboard)."""
        scene = tool_input.tool_args["scene"]
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": CURTAIN_SELECT, "option": scene},
            blocking=True,
            context=llm_context.context,
        )
        return {"success": True, "scene": scene, "note": "starts in a few seconds"}


SOUND_PLAYER = "media_player.skelly_music"
EFFECTS = "media-source://media_source/local/skelly/effects"
# Short cuts (1-6 s) of the public-domain library in /media/skelly/sounds; source
# copies in media/effects/ (deploy with tools/skelly.py deploy-media).
SOUNDS = {
    "evil_laugh": "slow evil laugh, 4 s",
    "evil_cackle": "wild cackling, 5 s",
    "wolf_howl": "a wolf pack howling, 6 s",
    "werewolf_howl": "a lone werewolf howl, 6 s",
    "raven": "ravens cawing, 4 s",
    "cat_hiss": "an angry cat hiss, 1 s",
    "door_creak": "a creaking door, 3 s",
    "rusty_door": "a rusty crypt door grinding open, 6 s",
    "knock_knock": "three slow knocks, 2 s",
    "church_bells": "tolling church bells, 6 s",
}


class PlaySoundTool(llm.Tool):
    """Play one short sound effect from the ground speaker."""

    name = "play_sound"

    def __init__(self, names: list[str]) -> None:
        """Offer only this personality's sounds."""
        self.description = (
            "Play a short sound effect from the speaker at your feet, at the "
            "same moment as your words. Sounds: "
            + "; ".join(f"{k} = {SOUNDS[k]}" for k in names)
            + "."
        )
        self.parameters = vol.Schema(
            {vol.Required("sound", description="Which sound effect"): vol.In(names)}
        )

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        """Play it as an announcement, so it ducks any ambient loop instead of stopping it."""
        sound = tool_input.tool_args["sound"]
        state = hass.states.get(SOUND_PLAYER)
        if state is None or state.state == "unavailable":
            return {"success": False, "error": "the sound speaker is switched off"}
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": SOUND_PLAYER,
                "media_content_id": f"{EFFECTS}/{sound}.mp3",
                "media_content_type": "music",
                "announce": True,
            },
            blocking=False,
            context=llm_context.context,
        )
        return {"success": True, "sound": sound}


SONGS_DIR = "media-source://media_source/local/skelly/songs"
# Suno songs in /media/skelly/songs/ (not in the repo: make your own from
# suno/song-prompts.md). Each has a ~1 minute jingle
# (<name>_short.mp3, cut at a section break with a fade) and the full ~3 minute
# song (<name>.mp3). Skelly plays the jingle unless someone asks for the whole song.
SONGS = {
    "skelly_on_the_mic": "your hip-hop rap about yourself, 'Skelly on the Microphone'",
    "shake_your_bones": "'Shake Your Bones', a bouncy singalong for little kids",
    "rest_in_puck": "'Rest in Puck', a pop-punk hockey anthem about your gravestone",
}


class PlaySongTool(llm.Tool):
    """Play one of Skelly's songs from the ground speaker."""

    name = "play_song"

    def __init__(self, names: list[str]) -> None:
        """Offer only this personality's songs."""
        self.description = (
            "Play one of your own songs from the speaker at your feet: a one-minute "
            "version, or the full three-minute song only if someone asks for the "
            "whole song. Songs: "
            + "; ".join(f"{k} = {SONGS[k]}" for k in names)
            + "."
        )
        self.parameters = vol.Schema(
            {
                vol.Required("song", description="Which song"): vol.In(names),
                vol.Optional(
                    "length", default="short", description="short (about 1 minute) or full (about 3 minutes)"
                ): vol.In(["short", "full"]),
            }
        )

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        """Play it as media, so sound effects still play over it (and duck it)."""
        song = tool_input.tool_args["song"]
        full = tool_input.tool_args.get("length") == "full"
        state = hass.states.get(SOUND_PLAYER)
        if state is None or state.state == "unavailable":
            return {"success": False, "error": "the music speaker is switched off"}
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": SOUND_PLAYER,
                "media_content_id": f"{SONGS_DIR}/{song}{'' if full else '_short'}.mp3",
                "media_content_type": "music",
            },
            blocking=False,
            context=llm_context.context,
        )
        return {"success": True, "song": song, "note": "about 3 minutes" if full else "about 1 minute"}


class StopSongTool(llm.Tool):
    """Stop whatever is playing on the ground speaker."""

    name = "stop_song"
    description = "Stop the music playing from the speaker at your feet."
    parameters = vol.Schema({})

    async def async_call(
        self, hass: HomeAssistant, tool_input: llm.ToolInput, llm_context: llm.LLMContext
    ) -> JsonObjectType:
        """Stop the music player."""
        await hass.services.async_call(
            "media_player",
            "media_stop",
            {"entity_id": SOUND_PLAYER},
            blocking=False,
            context=llm_context.context,
        )
        return {"success": True}


def _pick(choice: str | list[str] | None, catalog: dict[str, str]) -> list[str]:
    """A personality's "all" or list of names, limited to what exists."""
    if choice is None or choice == "all":
        return list(catalog)
    return [name for name in choice if name in catalog]


def personality_tools(hass: HomeAssistant) -> dict:
    """The current personality's tool choices (all sounds and songs if unknown)."""
    personas = hass.data.get(DOMAIN) or {}
    tools = personas.get("tools") or {}
    state = hass.states.get(PERSONALITY_SELECT)
    name = state.state if state and state.state in tools else personas.get("default")
    return tools.get(name, {})


def current_toolbox(hass: HomeAssistant) -> tuple[list[llm.Tool], str]:
    """Skelly's tools and their instructions right now: the personality's
    choices, and the light tools only after dark."""
    choices = personality_tools(hass)
    sounds, songs = _pick(choices.get("sounds"), SOUNDS), _pick(choices.get("songs"), SONGS)
    tools: list[llm.Tool] = []
    prompt = ""
    if sounds:
        tools.append(PlaySoundTool(sounds))
        prompt += SOUNDS_PROMPT
    if songs:
        tools += [PlaySongTool(songs), StopSongTool()]
        prompt += SONGS_PROMPT
    else:
        prompt += NO_SONGS_PROMPT
    if hass.states.is_state("sun.sun", "below_horizon"):
        prompt = LIGHTS_PROMPT + prompt
        tools.append(SetYardMoodTool())
        if names := curtain_scene_names(hass):
            tools.append(PlayCurtainSceneTool(names))
        if choices.get("show_workato"):
            prompt += WORKATO_LIGHTS_PROMPT
            tools.append(ShowWorkatoTool())
    else:
        prompt = DAYLIGHT_PROMPT + prompt
    return tools, prompt + NOTHING_ELSE_PROMPT


class SkellyToolsAPI(llm.API):
    """The yard-lights-only toolbox."""

    async def async_get_api_instance(self, llm_context: llm.LLMContext) -> llm.APIInstance:
        """Return the toolbox for one conversation turn (built fresh every turn)."""
        tools, prompt = current_toolbox(self.hass)
        return llm.APIInstance(api=self, api_prompt=prompt, llm_context=llm_context, tools=tools)


def _read_personas() -> dict:
    try:
        return json.loads(PERSONAS_FILE.read_text())
    except FileNotFoundError:
        return {}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the toolbox (loaded by `skelly_tools:` in configuration.yaml)."""
    hass.data[DOMAIN] = await hass.async_add_executor_job(_read_personas)

    async def reload_personas(call: ServiceCall) -> None:
        """Pick up a new personas.json (tools/skelly.py deploy-personas calls this)."""
        hass.data[DOMAIN] = await hass.async_add_executor_job(_read_personas)
        async_dispatcher_send(hass, SIGNAL_PERSONAS_RELOADED)

    hass.services.async_register(DOMAIN, "reload_personas", reload_personas)
    llm.async_register_api(
        hass, SkellyToolsAPI(hass=hass, id=DOMAIN, name="Skelly's yard lights and sounds")
    )
    # sensor.skelly_tools: what the dashboard shows as Skelly's tools right now.
    hass.async_create_task(discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config))
    return True
