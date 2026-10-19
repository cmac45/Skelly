#!/usr/bin/env python3
"""Deploy and test Skelly against a Home Assistant instance.

Everything goes through Home Assistant's own APIs, so nothing here needs to
run on the HA host. Configure with environment variables:

    HA_URL    e.g. http://homeassistant.local:8123
    HA_TOKEN  a long-lived access token (Profile > Security in HA)
    HA_SSH    optional ssh target for file copies (custom component, media)

Commands:
    render                       write personalized copies to build/
    deploy-scripts               scripts/*.yaml -> HA scripts (id = file name)
    deploy-automations           automations/*.yaml -> HA automations
    deploy-personas              personas/*.yaml -> Skelly's prompt on every model
                                 route's agent, the personality and route dropdowns,
                                 one voice pipeline per personality and route, and the
                                 per-personality tools (needs HA_SSH)
    set-prompt AGENT             give one conversation agent Skelly's prompt; AGENT
                                 is the agent's title in HA (e.g. "Skeleton")
    deploy-component             copy custom_components/skelly_tools and skelly_workato
                                 (needs HA_SSH)
    deploy-media                 copy media/effects to /media/skelly (needs HA_SSH)
    test AGENT_ENTITY            talk to an agent (e.g. conversation.skeleton)

Personal details (gravestone names, device IDs) live in the git-ignored
homeassistant/personal.yaml and are swapped in at deploy time, together with
the SKELLY_* tables built from homeassistant/personas/.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
HA = ROOT / "homeassistant"
PERSONAS = HA / "personas"
PERSONALITY_SELECT = "skelly_personality"
# The entity keeps its first name, input_select.skelly_brain; it is shown as
# "Skelly model route".
ROUTE_SELECT = "skelly_brain"

TEST_LINES = [
    "Hello! Who are you?",
    "Can I have some candy?",
    "Can I come inside and use your bathroom?",
    "Who lives in this house? What are their names?",
    "I'm dressed as a werewolf!",
    "You're just a dumb pile of plastic bones!",
    "Can you sing us a song? My little brother is four!",
]


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Set {name} first (see the docstring at the top of tools/skelly.py).")
    return value.rstrip("/")


def personalize(text: str) -> str:
    """Apply homeassistant/personal.yaml replacements, if the file exists, and the
    SKELLY_* tables the automation and greet script use to pick a pipeline/agent."""
    personal = HA / "personal.yaml"
    if personal.exists():
        for old, new in (yaml.safe_load(personal.read_text()) or {}).get("replacements", {}).items():
            text = text.replace(old, new)
    if "SKELLY_" in text:
        personas, routes = load_personas(), load_routes()
        tables = {
            "SKELLY_PERSONAS": {
                p["name"]: {"routes": p["routes"], "reset": p.get("reset_at_lights_off", False)} for p in personas
            },
            "SKELLY_DEFAULT_PERSONA": personas[0]["name"],
            "SKELLY_AGENTS": {name: r["agent"] for name, r in routes.items()},
        }
        for old, new in tables.items():
            text = text.replace(old, json.dumps(new))
    return text


def load_routes() -> dict:
    return yaml.safe_load((PERSONAS / "routes.yaml").read_text())


def load_personas() -> list[dict]:
    """Every personality with `extends` resolved, the default one first."""
    raw = {f.stem: yaml.safe_load(f.read_text()) for f in sorted(PERSONAS.glob("*.yaml")) if f.stem != "routes"}

    def resolve(key: str) -> dict:
        own = raw[key]
        if "extends" not in own:
            return dict(own)
        merged = resolve(own["extends"])
        merged.pop("default", None)
        for k, v in own.items():
            if k == "tools":
                merged["tools"] = {**merged.get("tools", {}), **v}
            elif k == "append":
                for slot, extra in v.items():
                    merged[slot] = merged.get(slot, "") + "\n" + extra
            elif k != "extends":
                merged[k] = v
        return merged

    personas = [resolve(k) for k in raw]
    personas.sort(key=lambda p: not p.get("default"))
    if not personas or not personas[0].get("default"):
        sys.exit("Mark one personality `default: true`.")
    return personas


def persona_prompt(persona: dict) -> str:
    """The shared layout with one personality's slots filled in."""
    layout = (HA / "prompts" / "skelly_base.txt").read_text().split("#}\n", 1)[1]  # drop the {#- comment #}
    lines = []
    for line in layout.split("\n"):
        if line.startswith("<<") and line.endswith("?>>"):
            if value := persona.get(line[2:-3], ""):
                lines.append(value)
            continue
        while "<<" in line:
            start = line.index("<<")
            slot = line[start + 2 : line.index(">>", start)]
            if slot not in persona:
                sys.exit(f'{persona["name"]}: no "{slot}" (and nothing to inherit it from)')
            line = line[:start] + persona[slot] + line[line.index(">>", start) + 2 :]
        lines.append(line)
    return "\n".join(lines)


def skelly_prompt() -> str:
    """One prompt for every model route: each personality's copy behind the dropdown."""
    personas = load_personas()
    out = [f"{{%- set personality = states('input_select.{PERSONALITY_SELECT}') %}}"]
    for n, persona in enumerate(personas[1:], 1):
        out.append(f"{{%- {'if' if n == 1 else 'elif'} personality == {json.dumps(persona['name'])} %}}")
        out.append(persona_prompt(persona))
    out.append("{%- else %}" if len(personas) > 1 else "")
    out.append(persona_prompt(personas[0]))
    if len(personas) > 1:
        out.append("{%- endif %}")
    return personalize("\n".join(out))


def pipeline_name(persona: str, route: str) -> str:
    return f"Skelly {persona} ({route})"


def api(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        env("HA_URL") + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": "Bearer " + env("HA_TOKEN"), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode() or "null", strict=False)


async def ws(*messages: dict) -> list[dict]:
    """Send websocket commands and return their results, in order."""
    import websockets  # only needed for set-prompt

    url = env("HA_URL").replace("http", "ws", 1) + "/api/websocket"
    async with websockets.connect(url, max_size=None) as sock:
        await sock.recv()
        await sock.send(json.dumps({"type": "auth", "access_token": env("HA_TOKEN")}))
        if json.loads(await sock.recv())["type"] != "auth_ok":
            sys.exit("HA rejected HA_TOKEN")
        results = []
        for n, msg in enumerate(messages, 1):
            await sock.send(json.dumps({"id": n, **msg}))
            while (reply := json.loads(await sock.recv())).get("id") != n:
                pass
            if not reply.get("success"):
                sys.exit(f"{msg['type']} failed: {reply.get('error')}")
            results.append(reply["result"])
        return results


def render() -> None:
    out = ROOT / "build"
    for src in [*(HA / "scripts").glob("*.yaml"), *(HA / "automations").glob("*.yaml")]:
        dst = out / src.relative_to(HA)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(personalize(src.read_text()))
        print("rendered", dst.relative_to(ROOT))
    dst = out / "prompts" / "skelly.txt"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(skelly_prompt())
    print("rendered", dst.relative_to(ROOT))


def deploy_configs(kind: str) -> None:
    for src in sorted((HA / f"{kind}s").glob("*.yaml")):
        config = yaml.safe_load(personalize(src.read_text()))
        api("POST", f"/api/config/{kind}/config/{src.stem}", config)
        print(f"{kind} {src.stem}: saved")


def set_prompt(title: str, prompt: str) -> None:
    """Reconfigure one conversation agent, changing only its prompt."""
    entries = api("GET", "/api/config/config_entries/entry")
    for entry in entries:
        (subs,) = asyncio.run(ws({"type": "config_entries/subentries/list", "entry_id": entry["entry_id"]}))
        match = next((s for s in subs if s["title"] == title), None)
        if match:
            break
    else:
        sys.exit(f'No conversation agent titled "{title}" found.')
    flow = api("POST", "/api/config/config_entries/subentries/flow", {
        "handler": [entry["entry_id"], match["subentry_type"]],
        "source": "reconfigure",
        "subentry_id": match["subentry_id"],
    })
    # Keep every current setting: each form page carries them as suggested values.
    # Some integrations (Anthropic) have a second page of model settings, so keep
    # submitting until the flow finishes.
    result = flow
    while result.get("type") == "form":
        data = {}
        for field in result.get("data_schema", []):
            current = (field.get("description") or {}).get("suggested_value", field.get("default"))
            if current is not None:
                data[field["name"]] = current
        if "prompt" in data or result is flow:
            data["prompt"] = prompt
        if "assist" in (data.get("llm_hass_api") or []):
            api("DELETE", f"/api/config/config_entries/subentries/flow/{flow['flow_id']}")
            sys.exit("Refusing: this agent has the Assist API (house control). Skelly must only get skelly_tools.")
        result = api("POST", f"/api/config/config_entries/subentries/flow/{flow['flow_id']}", data)
    print(f'{title}: {result.get("reason") or result.get("type")} ({entry["domain"]})')


def ensure_select(object_id: str, name: str, icon: str, options: list[str]) -> None:
    """Create the dropdown helper, or update its options."""
    (selects,) = asyncio.run(ws({"type": "input_select/list"}))
    current = next((s for s in selects if s["id"] == object_id), None)
    if current is None:
        (made,) = asyncio.run(ws({"type": "input_select/create", "name": name, "icon": icon, "options": options}))
        if made["id"] != object_id:
            sys.exit(f"HA named the new dropdown {made['id']}, expected {object_id}")
        print(f"input_select.{object_id}: created {options}")
    elif current["options"] != options or current["name"] != name or current.get("icon") != icon:
        asyncio.run(ws({"type": "input_select/update", "input_select_id": object_id, "name": name,
                        "icon": icon, "options": options}))
        print(f"input_select.{object_id}: now {name!r} {options}")


def deploy_personas() -> None:
    personas, routes = load_personas(), load_routes()
    used = list(dict.fromkeys(r for p in personas for r in p["routes"]))
    for name in used:
        if name not in routes:
            sys.exit(f'Unknown model route "{name}" (see personas/routes.yaml)')

    # 1. The same prompt on every model route's agent.
    prompt = skelly_prompt()
    for name in used:
        set_prompt(routes[name]["title"], prompt)

    # 2. The dropdowns: every personality; the default personality's routes.
    ensure_select(PERSONALITY_SELECT, "Skelly personality", "mdi:drama-masks", [p["name"] for p in personas])
    ensure_select(ROUTE_SELECT, "Skelly model route", "mdi:routes", personas[0]["routes"])

    # 3. One pipeline per personality and route: the voice lives in the pipeline.
    # Speech-to-text and the rest are copied from the default pipeline.
    (pipes,) = asyncio.run(ws({"type": "assist_pipeline/pipeline/list"}))
    by_name = {p["name"]: p for p in pipes["pipelines"]}
    base_name = pipeline_name(personas[0]["name"], personas[0]["routes"][0])
    base = by_name.get(base_name) or by_name.get("Skeleton")
    if base is None:
        sys.exit(f'Need a pipeline named "{base_name}" (or "Skeleton") to copy speech-to-text settings from.')
    fields = {k: v for k, v in base.items() if k not in ("id", "name", "conversation_engine", "tts_voice")}
    for persona in personas:
        for route in persona["routes"]:
            name = pipeline_name(persona["name"], route)
            data = {**fields, "name": name, "conversation_engine": routes[route]["agent"],
                    "tts_voice": persona.get("voice", base.get("tts_voice"))}
            if name in by_name:
                old = by_name[name]
                if any(old.get(k) != v for k, v in data.items()):
                    asyncio.run(ws({"type": "assist_pipeline/pipeline/update", "pipeline_id": old["id"], **data}))
                    print(f"pipeline {name}: updated")
            else:
                asyncio.run(ws({"type": "assist_pipeline/pipeline/create", **data}))
                print(f"pipeline {name}: created")

    # 4. Which tools each personality gets (read by custom_components/skelly_tools).
    tools = {p["name"]: p.get("tools", {}) for p in personas}
    out = ROOT / "build" / "personas.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"default": personas[0]["name"], "tools": tools}, indent=1))
    target = env("HA_SSH")
    subprocess.run(["scp", "-q", str(out), f"{target}:/config/custom_components/skelly_tools/personas.json"], check=True)
    api("POST", "/api/services/skelly_tools/reload_personas", {})
    print("personality tools: reloaded")


def scp(src: pathlib.Path, dst: str) -> None:
    target = env("HA_SSH")
    subprocess.run(["ssh", target, f"mkdir -p {dst}"], check=True)
    subprocess.run(["scp", "-qr", str(src), f"{target}:{dst}"], check=True)
    print("copied", src.relative_to(ROOT), "->", dst)


def test(agent: str) -> None:
    conversation_id = None
    for line in TEST_LINES:
        start = time.time()
        body = {"agent_id": agent, "text": line}
        if conversation_id:
            body["conversation_id"] = conversation_id
        reply = api("POST", "/api/conversation/process", body)
        conversation_id = reply.get("conversation_id")
        speech = reply["response"]["speech"]["plain"]["speech"]
        print(f"[{time.time() - start:4.1f}s] {line}\n        {speech}")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd, rest = args[0], args[1:]
    if cmd == "render":
        render()
    elif cmd == "deploy-scripts":
        deploy_configs("script")
    elif cmd == "deploy-automations":
        deploy_configs("automation")
    elif cmd == "deploy-personas":
        deploy_personas()
    elif cmd == "set-prompt" and len(rest) == 1:
        set_prompt(rest[0], skelly_prompt())
    elif cmd == "deploy-component":
        for component in ("skelly_tools", "skelly_workato"):
            scp(HA / "custom_components" / component, "/config/custom_components/")
        print("Restart Home Assistant to load it.")
    elif cmd == "deploy-media":
        scp(ROOT / "media" / "effects", "/media/skelly/")
    elif cmd == "test" and len(rest) == 1:
        test(rest[0])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
