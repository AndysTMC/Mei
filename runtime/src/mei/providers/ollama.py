"""Ollama native chat adapter (`/api/chat`, NDJSON). Errors arrive as `{"error": …}` lines."""

from collections.abc import AsyncIterator

import httpx

from .base import Done, ModelEvent, ModelRequest, ProviderError, TextDelta, ThinkingDelta, Usage
from .http_stream import first_int, loads, stream_post


class OllamaProvider:
    def __init__(self, client: httpx.AsyncClient, *, label: str, url: str, model: str, api_key: str = "") -> None:
        if not model:
            raise ProviderError(f"{label}: no model selected")
        self.label = label
        self.model = model
        self._client = client
        self._url = url
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def body(self, request: ModelRequest) -> dict:
        return {"model": self.model, "stream": True,
                "messages": [{"role": t.role, "content": t.content} for t in request.messages],
                "think": "medium" if "gpt-oss" in self.model.lower() else True}

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
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
            if obj.get("done"):
                yield Usage(first_int(obj, "prompt_eval_count"), first_int(obj, "eval_count"))
                break
        yield Done("stop")
