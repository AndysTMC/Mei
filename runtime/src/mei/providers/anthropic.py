"""Anthropic Messages API adapter (streaming). Also serves OpenCode models routed to `/messages`."""

import re
from collections.abc import AsyncIterator

import httpx

from .base import Done, ModelEvent, ModelRequest, ProviderError, TextDelta, ThinkingDelta, Usage
from .http_stream import error_message, first_int, loads, stream_post

MAX_TOKENS = 4096
_ADAPTIVE_THINKING = re.compile(r"(?:opus-4-[678]|sonnet-4-6|fable-5|sonnet-5|mythos-5)")


class AnthropicProvider:
    def __init__(self, client: httpx.AsyncClient, *, label: str, url: str, model: str, api_key: str = "",
                 bearer_auth: bool = False, headers: dict[str, str] | None = None) -> None:
        if not model:
            raise ProviderError(f"{label}: no model selected")
        self.label = label
        self.model = model
        self._client = client
        self._url = url
        auth = {} if not api_key else ({"Authorization": f"Bearer {api_key}"} if bearer_auth else {"x-api-key": api_key})
        self._headers = {**(headers or {}), **auth, "anthropic-version": "2023-06-01"}

    def body(self, request: ModelRequest) -> dict:
        system = "\n\n".join(t.content for t in request.messages if t.role == "system")
        body = {"model": self.model, "max_tokens": MAX_TOKENS, "stream": True,
                "messages": [{"role": t.role, "content": t.content} for t in request.messages if t.role != "system"]}
        if system:
            body["system"] = system
        if _ADAPTIVE_THINKING.search(self.model.lower()):
            body["thinking"] = {"type": "adaptive", "display": "summarized"}
        return body

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        input_tokens = None
        async for data in stream_post(self._client, self._url, self.body(request), self._headers, label=self.label):
            event = loads(data)
            if event is None:
                continue
            kind = event.get("type")
            if kind == "error":
                raise ProviderError(f"{self.label}: {error_message(event) or 'stream error'}",
                                    retryable=_overloaded(event))
            if kind == "message_start":
                usage = (event.get("message") or {}).get("usage") or {}
                input_tokens = first_int(usage, "input_tokens")
            elif kind == "content_block_delta":
                delta = event.get("delta") or {}
                if delta.get("type") == "text_delta" and delta.get("text"):
                    yield TextDelta(delta["text"])
                elif delta.get("type") == "thinking_delta" and delta.get("thinking"):
                    yield ThinkingDelta(delta["thinking"])
            elif kind == "message_delta":
                usage = event.get("usage") or {}
                yield Usage(input_tokens, first_int(usage, "output_tokens"))
            elif kind == "message_stop":
                break
        yield Done("stop")


def _overloaded(event: dict) -> bool:
    err = event.get("error")
    return isinstance(err, dict) and err.get("type") in ("overloaded_error", "rate_limit_error", "api_error")
