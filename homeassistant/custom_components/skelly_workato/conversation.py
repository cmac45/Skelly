"""The conversation agent: HA chat log <-> Workato chat completions, streamed."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
import json
from typing import Any, Literal

import aiohttp
from probatio import to_openapi

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigSubentry
from homeassistant.const import CONF_MODEL, CONF_PROMPT, MATCH_ALL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, llm
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.json import json_dumps

from . import WorkatoConfigEntry
from .const import BASE_URL, CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS, DOMAIN, LLM_API, LOGGER

MAX_TOOL_ITERATIONS = 10


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: WorkatoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One conversation entity per agent subentry."""
    for subentry_id, subentry in config_entry.subentries.items():
        if subentry.subentry_type == "conversation":
            async_add_entities(
                [WorkatoConversationEntity(config_entry, subentry)],
                config_subentry_id=subentry_id,
            )


def _format_tool(tool: llm.Tool, custom_serializer: Callable[[Any], Any] | None) -> dict[str, Any]:
    """An HA tool as an OpenAI function definition."""
    schema = to_openapi(tool.parameters, custom_serializer=custom_serializer)
    schema = {k: v for k, v in schema.items() if k not in {"oneOf", "anyOf", "allOf"}}
    function: dict[str, Any] = {"name": tool.name, "parameters": schema}
    if tool.description:
        function["description"] = tool.description
    return {"type": "function", "function": function}


def _to_message(content: conversation.Content) -> dict[str, Any] | None:
    """A chat log entry as an OpenAI chat message."""
    if isinstance(content, conversation.ToolResultContent):
        return {"role": "tool", "tool_call_id": content.tool_call_id, "content": json_dumps(content.tool_result)}
    role: Literal["user", "assistant", "system"] = content.role
    if role in ("system", "user") and content.content:
        return {"role": role, "content": content.content}
    if role == "assistant":
        message: dict[str, Any] = {"role": "assistant", "content": content.content}
        if isinstance(content, conversation.AssistantContent) and content.tool_calls:
            message["tool_calls"] = [
                {
                    "type": "function",
                    "id": call.id,
                    "function": {"name": call.tool_name, "arguments": json_dumps(call.tool_args)},
                }
                for call in content.tool_calls
            ]
        return message
    return None


async def _stream_deltas(
    resp: aiohttp.ClientResponse,
) -> AsyncGenerator[conversation.AssistantContentDeltaDict]:
    """Turn the server-sent events into chat log deltas.

    Text goes out as it arrives; tool calls come in pieces (name first, then the
    JSON arguments a few characters at a time) and go out whole at the end. A
    reply cut off at max_tokens can end mid-call; such a call is dropped rather
    than run with missing arguments.
    """
    yield {"role": "assistant"}
    calls: dict[int, dict[str, str]] = {}
    finish = None
    async for raw in resp.content:
        line = raw.decode().strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        chunk = json.loads(payload)
        if error := chunk.get("error"):
            raise HomeAssistantError(f"Workato error: {error}")
        for choice in chunk.get("choices") or []:
            finish = choice.get("finish_reason") or finish
            delta = choice.get("delta") or {}
            if text := delta.get("content"):
                yield {"content": text}
            for piece in delta.get("tool_calls") or []:
                call = calls.setdefault(piece.get("index", 0), {"id": "", "name": "", "arguments": ""})
                call["id"] = piece.get("id") or call["id"]
                function = piece.get("function") or {}
                call["name"] = function.get("name") or call["name"]
                call["arguments"] += function.get("arguments") or ""
    if finish == "length":
        LOGGER.warning("Workato reply hit max_tokens; raise it or check the route's thinking setting")
    tool_calls = []
    for _, c in sorted(calls.items()):
        try:
            args = json.loads(c["arguments"] or "{}")
        except json.JSONDecodeError:
            args = None
        if not isinstance(args, dict) or (finish == "length" and not c["arguments"]):
            LOGGER.warning("Dropping incomplete %s call from Workato: %r", c["name"], c["arguments"])
            continue
        tool_calls.append(llm.ToolInput(id=c["id"], tool_name=c["name"], tool_args=args))
    if tool_calls:
        yield {"tool_calls": tool_calls}


class WorkatoConversationEntity(conversation.ConversationEntity):
    """A Skelly agent whose brain is reached through the Workato AI Gateway."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supports_streaming = True
    _attr_supported_features = conversation.ConversationEntityFeature.CONTROL

    def __init__(self, entry: WorkatoConfigEntry, subentry: ConfigSubentry) -> None:
        """Initialize the agent."""
        self.entry = entry
        self.subentry = subentry
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="Workato",
            model=subentry.data[CONF_MODEL],
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Whatever the model speaks."""
        return MATCH_ALL

    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: conversation.ChatLog,
    ) -> conversation.ConversationResult:
        """Answer one turn, running Skelly's tools as the model asks for them."""
        options = self.subentry.data
        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                [LLM_API],
                options.get(CONF_PROMPT),
                user_input.extra_system_prompt,
            )
        except conversation.ConverseError as err:
            return err.as_conversation_result()

        body: dict[str, Any] = {
            "model": options[CONF_MODEL],
            "stream": True,
            "max_tokens": options.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
            "user": chat_log.conversation_id,
            # Workato's route has extended thinking on. Its tokens count against
            # max_tokens (200 cut replies and tool calls short) and it delays the
            # first words, so it's off for Skelly.
            "reasoning_effort": "none",
        }
        if chat_log.llm_api:
            body["tools"] = [_format_tool(t, chat_log.llm_api.custom_serializer) for t in chat_log.llm_api.tools]
        messages = [m for content in chat_log.content if (m := _to_message(content))]

        session = async_get_clientsession(self.hass)
        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                async with session.post(
                    f"{BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {self.entry.runtime_data}"},
                    json={**body, "messages": messages},
                    timeout=aiohttp.ClientTimeout(total=60, sock_read=30),
                ) as resp:
                    if resp.status != 200:
                        LOGGER.error("Workato returned %s: %s", resp.status, await resp.text())
                        raise HomeAssistantError(f"Workato returned {resp.status}")
                    messages.extend(
                        [
                            m
                            async for content in chat_log.async_add_delta_content_stream(
                                self.entity_id, _stream_deltas(resp)
                            )
                            if (m := _to_message(content))
                        ]
                    )
            except aiohttp.ClientError as err:
                LOGGER.error("Error talking to Workato: %s", err)
                raise HomeAssistantError("Error talking to Workato") from err
            if not chat_log.unresponded_tool_results:
                break

        return conversation.async_get_result_from_chat_log(user_input, chat_log)
