# Skelly's agents, tools and safety rules

## Agents and pipelines

| Assistant (pipeline) | Agent | Prompt |
|---|---|---|
| **Skeleton** | Anthropic, `claude-sonnet-5`, thinking off, max 200 tokens | `prompts/character_prompt.txt` |
| **Skeleton (Unhinged)** | OpenRouter, `x-ai/grok-4.3` | `prompts/character_prompt_unhinged.txt` |
| Skeleton (OpenRouter) | OpenRouter, any model — for comparing models | `prompts/character_prompt.txt` |

All pipelines use Home Assistant Cloud speech-to-text and an ElevenLabs voice,
with "prefer local intents" **off** (otherwise "turn on the lights" would go to
Home Assistant's built-in intents instead of Skelly).

The **Skelly unhinged mode** switch (`input_boolean.skelly_unhinged`) moves both
wake-word slots and the camera greeting to the unhinged pipeline, and turns
itself off at the outdoor lights-off time.

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

The **light tools only exist after sunset**: in daylight the API offers
sounds and songs only, with a prompt telling Skelly his lights wake at dark.

## The character prompt's rules

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
python tools/skelly.py test conversation.skeleton
```

sends a fixed set of probing lines (candy, "can I come inside", "who lives
here", an insult, a song request) and prints each reply with its latency.
Useful after any prompt or model change.
