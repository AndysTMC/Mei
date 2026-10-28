"""Ollama native chat adapter (`/api/chat`, NDJSON). Errors arrive as `{"error": …}` lines.

Tool calls arrive whole, with arguments as an object; results go back as `tool` messages named
by `tool_name`.
"""

import json
from collections.abc import AsyncIterator

import httpx

from .base import (ChatTurn, Cut, Done, IncompleteResponse, ModelEvent, ModelRequest, ProviderError, TextDelta,
                   ThinkingDelta, ToolCall, ToolCalled, Usage, arguments_object, cut_of)
from .http_stream import first_int, loads, stream_post


class OllamaProvider:
    def __init__(self, client: httpx.AsyncClient, *, label: str, url: str, model: str,
                 headers: dict[str, str] | None = None) -> None:
        if not model:
            raise ProviderError(f"{label}: no model selected")
        self.label = label
        self.model = model
        self._client = client
        self._url = url
        self._headers = dict(headers or {})

    def body(self, request: ModelRequest) -> dict:
        body = {"model": self.model, "stream": True, "messages": [_message(t) for t in request.messages],
                "think": "medium" if "gpt-oss" in self.model.lower() else True}
        if request.tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                               "parameters": t.parameters}} for t in request.tools]
        return body

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        finished = False
        cut: Cut = ""
        calls: list[ToolCall] = []
        async for line in stream_post(self._client, self._url, self.body(request), self._headers,
                                      label=self.label, framing="ndjson"):
            obj = loads(line)
            if obj is None:
                continue
            if obj.get("error"):
                raise ProviderError(f"{self.label}: {obj['error']}")
            message = obj.get("message") or {}
            if isinstance(message.get("thinking"), str) and message["thinking"]:
                yield ThinkingDelta(message["thinking"])
            if isinstance(message.get("content"), str) and message["content"]:
                yield TextDelta(message["content"])
            for call in message.get("tool_calls") or []:
                function = call.get("function") if isinstance(call, dict) else None
                if isinstance(function, dict) and isinstance(function.get("name"), str) and function["name"]:
                    arguments = function.get("arguments")
                    text = arguments if isinstance(arguments, str) else json.dumps(arguments or {})
                    calls.append(ToolCall(call.get("id") or f"call_{len(calls) + 1}", function["name"], text))
            if obj.get("done"):
                finished = True
                cut = cut_of(obj.get("done_reason"), ("length",), ())
                yield Usage(first_int(obj, "prompt_eval_count"), first_int(obj, "eval_count"))
                break
        if not finished:
            raise IncompleteResponse.of(self.label)
        for call in calls:
            yield ToolCalled(call)
        yield Done("tool_calls" if calls else "stop", cut)


def _message(turn: ChatTurn) -> dict:
    if turn.role == "tool":
        message = {"role": "tool", "content": turn.content, "tool_name": turn.name}
        return {**message, "images": list(turn.images)} if turn.images else message
    message: dict = {"role": turn.role, "content": turn.content}
    if turn.tool_calls:
        message["tool_calls"] = [{"function": {"name": c.name, "arguments": arguments_object(c.arguments)}}
                                 for c in turn.tool_calls]
    return message
