"""OpenAI-compatible Chat Completions adapter (streaming).

Serves OpenAI, Groq, Mistral, OpenRouter, DeepSeek, Fireworks, NVIDIA, llama.cpp, LM Studio, and
custom URLs. Reasoning is separated from the answer by `StreamNormalizer`, whatever shape the
provider uses. Tool calls arrive as fragments keyed by `index` and are assembled here.
"""

import json
from collections.abc import AsyncIterator

import httpx

from .base import (ChatTurn, Done, IncompleteResponse, ModelEvent, ModelRequest, ProviderError, Replay,
                   ReplayData, TextDelta, ThinkingDelta, ToolCall, ToolCalled, Usage, replay_for)
from .http_stream import MAX_RESPONSE_BYTES, error_message, first_int, loads, stream_post
from .openai_normalize import StreamNormalizer

__all__ = ["OpenAIChatProvider", "MAX_RESPONSE_BYTES"]
WIRE = "openai_chat"


class OpenAIChatProvider:
    def __init__(self, client: httpx.AsyncClient, *, label: str, url: str, model: str,
                 headers: dict[str, str] | None = None, extra_body: dict | None = None,
                 echo_reasoning: bool = False) -> None:
        """`echo_reasoning`: send a tool-calling turn's reasoning back as `reasoning_content` (DeepSeek
        requires it within one question; other providers reject the unknown field)."""
        if not url.startswith(("https://", "http://")):
            raise ProviderError(f"{label}: endpoint must be an http(s) URL")
        if not model:
            raise ProviderError(f"{label}: no model selected")
        self.label = label
        self.model = model
        self._client = client
        self._url = url
        self._headers = dict(headers or {})
        self._extra = dict(extra_body or {})
        self._echo_reasoning = echo_reasoning

    def body(self, request: ModelRequest) -> dict:
        body = {"model": self.model, "stream": True,
                "messages": [self._message(t) for t in request.messages], **self._extra}
        if request.tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                               "parameters": t.parameters}} for t in request.tools]
        return body

    def _message(self, turn: ChatTurn) -> dict:
        if turn.role == "tool":
            return {"role": "tool", "tool_call_id": turn.tool_call_id, "content": turn.content}
        if turn.role != "assistant" or not turn.tool_calls:
            return {"role": turn.role, "content": turn.content}
        message: dict = {"role": "assistant", "content": turn.content or None,
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.name, "arguments": c.arguments}}
                                        for c in turn.tool_calls]}
        replay = replay_for(turn, WIRE) or {}
        if replay.get("reasoning_details"):
            message["reasoning_details"] = replay["reasoning_details"]
        if self._echo_reasoning and replay.get("reasoning_content"):
            message["reasoning_content"] = replay["reasoning_content"]
        return message

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        normalizer = StreamNormalizer()
        calls = CallAssembler()
        details: list[dict] = []
        reasoning = ""  # DeepSeek's `reasoning_content`, exactly as sent
        finished = False  # `[DONE]` or a finish_reason; without either the reply may be cut off
        async for data in stream_post(self._client, self._url, self.body(request), self._headers, label=self.label):
            if data.strip() == "[DONE]":
                finished = True
                break
            obj = loads(data)
            if obj is None:
                continue
            if obj.get("error"):
                raise ProviderError(f"{self.label}: {error_message(obj) or 'stream error'}")
            for choice in obj.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                if choice.get("finish_reason"):
                    finished = True
                delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                calls.feed(delta.get("tool_calls"))
                merge_reasoning_details(details, delta.get("reasoning_details"))
                if isinstance(delta.get("reasoning_content"), str):
                    reasoning += delta["reasoning_content"]
            usage = obj.get("usage")
            if isinstance(usage, dict):
                yield Usage(first_int(usage, "prompt_tokens", "input_tokens"),
                            first_int(usage, "completion_tokens", "output_tokens"))
            text, thinking = normalizer.consume(obj)
            if thinking:
                yield ThinkingDelta(thinking)
            if text:
                yield TextDelta(text)
        text, thinking = normalizer.flush()
        if thinking:
            yield ThinkingDelta(thinking)
        if text:
            yield TextDelta(text)
        if not finished:
            raise IncompleteResponse.of(self.label)
        assembled = calls.calls()
        for call in assembled:
            yield ToolCalled(call)
        if assembled and (details or (self._echo_reasoning and reasoning)):
            replay: dict = {}
            if details:
                replay["reasoning_details"] = details
            if self._echo_reasoning and reasoning:
                replay["reasoning_content"] = reasoning
            yield ReplayData(Replay(WIRE, replay))
        yield Done("tool_calls" if assembled else "stop")


class CallAssembler:
    """Joins streamed tool-call fragments. Fragments name their call by `index`; some providers
    send whole calls without one, which then count by position."""

    def __init__(self) -> None:
        self._slots: dict[object, dict] = {}

    def feed(self, fragments: object) -> None:
        if not isinstance(fragments, list):
            return
        for position, fragment in enumerate(fragments):
            if not isinstance(fragment, dict):
                continue
            key = fragment["index"] if isinstance(fragment.get("index"), int) else (fragment.get("id") or position)
            slot = self._slots.setdefault(key, {"id": "", "name": "", "arguments": ""})
            function = fragment.get("function") if isinstance(fragment.get("function"), dict) else {}
            if isinstance(fragment.get("id"), str) and fragment["id"]:
                slot["id"] = fragment["id"]
            if isinstance(function.get("name"), str) and function["name"]:
                slot["name"] = function["name"]
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                slot["arguments"] += arguments
            elif isinstance(arguments, dict):
                slot["arguments"] = json.dumps(arguments)

    def calls(self) -> list[ToolCall]:
        return [ToolCall(slot["id"] or f"call_{n}", slot["name"], slot["arguments"] or "{}")
                for n, slot in enumerate(self._slots.values(), start=1) if slot["name"]]


def merge_reasoning_details(acc: list[dict], items: object) -> None:
    """OpenRouter streams reasoning details in pieces; it wants them back whole on the next request."""
    if not isinstance(items, list):
        return
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        index = item.get("index", position)
        target = next((d for d in acc if d["index"] == index and d.get("type") == item.get("type")), None)
        if target is None:
            acc.append({**item, "index": index})
            continue
        for key, value in item.items():
            if key in ("text", "summary", "data") and isinstance(value, str):
                target[key] = (target.get(key) or "") + value
            elif value is not None and key != "index":
                target[key] = value
