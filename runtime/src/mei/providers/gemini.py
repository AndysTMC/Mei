"""Google Gemini adapter (`streamGenerateContent?alt=sse`). The key goes in a header, never the URL.

Function calls arrive whole, each part possibly carrying a thought signature that Gemini 3
requires back on the same part in the next request. Results for one turn go back in one content.
"""

import json
import re
from collections.abc import AsyncIterator
from urllib.parse import quote

import httpx

from .base import (ChatTurn, Cut, Done, IncompleteResponse, ModelEvent, ModelRequest, ProviderError, TextDelta,
                   ThinkingDelta, ToolCall, ToolCalled, Usage, arguments_object, cut_of, tool_groups)
from .http_stream import error_message, first_int, loads, stream_post

_THOUGHT_SUMMARIES = re.compile(r"^gemini-(?:2\.5|3(?:\.|-))")


class GeminiProvider:
    def __init__(self, client: httpx.AsyncClient, *, label: str, base_url: str, model: str,
                 headers: dict[str, str] | None = None) -> None:
        if not model:
            raise ProviderError(f"{label}: no model selected")
        self.label = label
        self.model = model
        self._client = client
        self._url = f"{base_url.rstrip('/')}/models/{quote(model, safe='')}:streamGenerateContent?alt=sse"
        self._headers = dict(headers or {})

    def body(self, request: ModelRequest) -> dict:
        system = [{"text": t.content} for t in request.messages if t.role == "system"]
        body: dict = {"contents": _contents([t for t in request.messages if t.role != "system"])}
        if system:
            body["systemInstruction"] = {"parts": system}
        if request.tools:
            body["tools"] = [{"functionDeclarations": [{"name": t.name, "description": t.description,
                                                        "parameters": t.parameters} for t in request.tools]}]
        if _THOUGHT_SUMMARIES.search(self.model.lower()):
            body["generationConfig"] = {"thinkingConfig": {"includeThoughts": True}}
        return body

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        finished = False  # Gemini marks the last chunk with a finishReason
        cut: Cut = ""
        calls: list[ToolCall] = []
        async for data in stream_post(self._client, self._url, self.body(request), self._headers, label=self.label):
            obj = loads(data)
            if obj is None:
                continue
            if obj.get("error"):
                raise ProviderError(f"{self.label}: {error_message(obj) or 'stream error'}")
            for candidate in obj.get("candidates") or []:
                if isinstance(candidate, dict) and candidate.get("finishReason"):
                    finished = True
                    cut = cut or cut_of(candidate["finishReason"], ("max_tokens",), (
                        "safety", "recitation", "blocklist", "prohibited_content", "spii", "image_safety"))
                parts = ((candidate or {}).get("content") or {}).get("parts") or []
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    call = part.get("functionCall")
                    if isinstance(call, dict) and isinstance(call.get("name"), str) and call["name"]:
                        args = call.get("args") if isinstance(call.get("args"), dict) else {}
                        calls.append(ToolCall(call.get("id") or f"call_{len(calls) + 1}", call["name"],
                                              json.dumps(args), signature=part.get("thoughtSignature") or ""))
                        continue
                    if not isinstance(part.get("text"), str) or not part["text"]:
                        continue
                    yield ThinkingDelta(part["text"]) if part.get("thought") is True else TextDelta(part["text"])
            usage = obj.get("usageMetadata")
            if isinstance(usage, dict):
                yield Usage(first_int(usage, "promptTokenCount"), first_int(usage, "candidatesTokenCount"))
        if not finished:
            raise IncompleteResponse.of(self.label)
        for call in calls:
            yield ToolCalled(call)
        yield Done("tool_calls" if calls else "stop", cut)


def _contents(turns: list[ChatTurn]) -> list[dict]:
    out: list[dict] = []
    for item in tool_groups(turns):
        if isinstance(item, list):
            out.append({"role": "user", "parts": [*(_function_response(t) for t in item),
                                                  *({"inline_data": {"mime_type": "image/png", "data": data}}
                                                    for t in item for data in t.images)]})
        elif item.role == "assistant":
            parts: list[dict] = [{"text": item.content}] if item.content else []
            for call in item.tool_calls:
                part: dict = {"functionCall": {"name": call.name, "args": arguments_object(call.arguments)}}
                if call.signature:
                    part["thoughtSignature"] = call.signature
                parts.append(part)
            out.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif out and out[-1]["role"] == "user":
            out[-1]["parts"].append({"text": item.content})  # a steer right after tool results
        else:
            out.append({"role": "user", "parts": [{"text": item.content}]})
    return out


def _function_response(turn: ChatTurn) -> dict:
    key = "error" if turn.is_error else "result"
    return {"functionResponse": {"name": turn.name, "response": {key: turn.content}}}

