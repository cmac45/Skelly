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
    set-prompt AGENT normal|unhinged
                                 replace a conversation agent's prompt; AGENT is
                                 the agent's title in HA (e.g. "Skeleton")
    deploy-component             copy custom_components/skelly_tools (needs HA_SSH)
    deploy-media                 copy media/effects to /media/skelly (needs HA_SSH)
    test AGENT_ENTITY            talk to an agent (e.g. conversation.skeleton)

Personal details (gravestone names, device IDs) live in the git-ignored
homeassistant/personal.yaml and are swapped in at deploy time.
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
PROMPTS = {"normal": "character_prompt.txt", "unhinged": "character_prompt_unhinged.txt"}

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
    """Apply homeassistant/personal.yaml replacements, if the file exists."""
    personal = HA / "personal.yaml"
    if personal.exists():
        for old, new in (yaml.safe_load(personal.read_text()) or {}).get("replacements", {}).items():
            text = text.replace(old, new)
    return text


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
    for src in [*(HA / "prompts").glob("*.txt"), *(HA / "scripts").glob("*.yaml"), *(HA / "automations").glob("*.yaml")]:
        dst = out / src.relative_to(HA)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(personalize(src.read_text()))
        print("rendered", dst.relative_to(ROOT))


def deploy_configs(kind: str) -> None:
    for src in sorted((HA / f"{kind}s").glob("*.yaml")):
        config = yaml.safe_load(personalize(src.read_text()))
        api("POST", f"/api/config/{kind}/config/{src.stem}", config)
        print(f"{kind} {src.stem}: saved")


def set_prompt(title: str, which: str) -> None:
    """Reconfigure one conversation agent, changing only its prompt."""
    prompt = personalize((HA / "prompts" / PROMPTS[which]).read_text())
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
    # Keep every current setting: the form carries them as suggested values.
    data = {}
    for field in flow.get("data_schema", []):
        current = (field.get("description") or {}).get("suggested_value", field.get("default"))
        if current is not None:
            data[field["name"]] = current
    data["prompt"] = prompt
    if "assist" in (data.get("llm_hass_api") or []):
        sys.exit("Refusing: this agent has the Assist API (house control). Skelly must only get skelly_tools.")
    result = api("POST", f"/api/config/config_entries/subentries/flow/{flow['flow_id']}", data)
    print(f'{title}: {result.get("reason") or result.get("type")} ({entry["domain"]})')


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
    elif cmd == "set-prompt" and len(rest) == 2 and rest[1] in PROMPTS:
        set_prompt(*rest)
    elif cmd == "deploy-component":
        scp(HA / "custom_components" / "skelly_tools", "/config/custom_components/")
        print("Restart Home Assistant to load it.")
    elif cmd == "deploy-media":
        scp(ROOT / "media" / "effects", "/media/skelly/")
    elif cmd == "test" and len(rest) == 1:
        test(rest[0])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
