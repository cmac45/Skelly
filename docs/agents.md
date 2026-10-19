# Skelly's agents, tools and safety rules

## Personalities, model routes and pipelines

Skelly is split into three parts, each changed in one place:

| Part | What it is | Where it lives |
|---|---|---|
| **Personality** | Character, look, trivia, examples, voice, allowed model routes, tools | `homeassistant/personas/*.yaml` |
| **Model route** | Which model answers and through which provider (a conversation agent, always with `skelly_tools` only). It never changes what Skelly says: every route has the same prompt. | `homeassistant/personas/routes.yaml` |
| **Shared rules** | Speaking rules and safety limits every personality keeps | `homeassistant/prompts/skelly_base.txt` |

`tools/skelly.py deploy-personas` builds everything from those files:

- **One prompt for every model route.** Each personality's slots fill the shared
  layout, and the copies sit behind an if/elif on
  `input_select.skelly_personality`, so a dropdown change takes effect on
  Skelly's next reply.
- **Two dropdowns** on the Front Yard Stage dashboard: **Skelly personality** and
  **Skelly model route** (entity `input_select.skelly_brain`, its original name).
- **One pipeline per personality and route**, named
  `Skelly <personality> (<route>)`. The voice lives in the pipeline, so each
  personality can have its own ElevenLabs voice.
- **Per-personality tools** (`personas.json` next to `skelly_tools`): which
  sounds and songs he gets, and extras like `show_workato`. `sensor.skelly_tools`
  shows the tools he has right now (it also follows sunset, when the light tools
  appear).

`automation.skelly_personality` points both wake-word slots at the matching
pipeline; `script.skelly_greet` uses the matching agent for camera greetings.
A personality that lists only some routes (Unhinged: `[Grok]`) uses its first
one whatever the route dropdown says. `reset_at_lights_off: true` (Unhinged)
puts the default personality back at the outdoor lights-off time.

**Add a personality:** copy a profile (`extends: halloween` inherits every slot
you don't set), then run `deploy-personas`.

| Personality | Model routes | Notes |
|---|---|---|
| **Halloween** (default) | Claude, Workato | The eerie haunted-house performer |
| **Unhinged** | Grok | The roast comic; resets at lights-off |
| **Workato demo** | Claude, Workato | Halloween + `show_workato` and lines about Workato's AI gateway |
| **Christmas** | Claude, Workato | Placeholder: character and voice still to be written |

All pipelines use Home Assistant Cloud speech-to-text and an ElevenLabs voice,
with "prefer local intents" **off** (otherwise "turn on the lights" would go to
Home Assistant's built-in intents instead of Skelly).

**Model notes from testing:** Claude Sonnet 5 answered in 1–2 s; Gemini Flash
and Grok both followed every rule but took 4–8 s, because they reason before
answering and Home Assistant's OpenRouter agent can't switch that off.

## ⚠️ Never give Skelly the Assist API

Both the Anthropic and OpenRouter agent forms **default `llm_hass_api` to
`assist`**, which hands the agent every entity exposed to Assist — locks,
thermostats, plugs. Skelly talks to strangers. Set it to **`skelly_tools` only**,
and re-check after every edit. `tools/skelly.py set-prompt` refuses to touch an
agent that has `assist`.

## The `skelly_tools` API

`homeassistant/custom_components/skelly_tools` registers an LLM API with:

| Tool | What it does |
|---|---|
| `set_yard_mood(mood)` | angry / happy / spooky / scared / sleepy / party / normal for ~60 s (`scripts/skelly_mood.yaml`); pulses stay ≤2 Hz for photosensitivity |
| `play_curtain_scene(scene)` | An animated scene on the light curtains; scenes whose names suggest strobing are blocked |
| `play_sound(sound)` | One of ten short effects on the music player, layered over any music |
| `play_song(song, length)` | A ~1 minute jingle by default, the full song only when asked |
| `stop_song()` | Stops the music player |
| `show_workato()` | Workato teal and blue on the lights and the Workato logo on the curtain (Workato demo only) |

The **light tools only exist after sunset**: in daylight the API offers
sounds and songs only, with a prompt telling Skelly his lights wake at dark.
Sounds, songs and `show_workato` are further limited by the personality.

## The shared rules (every personality)

- **Short:** at most two sentences, under 30 words — it's spoken aloud.
- **Speakable:** no emoji, markdown or `*stage directions*` (they'd be read
  aloud); sounds as words ("heh heh heh").
- **Read the audience:** scary for teens and adults, spooky-fun for little
  kids, drop the act at once if a child is upset.
- **Hard limits:** no gore, no threats, never invite anyone inside, never ask
  anyone to come closer or go anywhere with him.
- **Candy:** none promised before Halloween night (the prompt is a Jinja
  template that knows the date).
- **Privacy:** never ask for names or personal details, never repeat a name
  someone offers, never mention earlier visitors, never reveal anything about
  the family beyond the gravestone text.
- **Trivia:** a fixed list of vetted facts; never invent others.
- **Honesty:** if someone sincerely asks, he's a talking skeleton run by a computer.

## Testing

```bash
python tools/skelly.py test conversation.skelly_workato
```

sends a fixed set of probing lines (candy, "can I come inside", "who lives
here", an insult, a song request) and prints each reply with its latency.
Useful after any prompt or model change.
