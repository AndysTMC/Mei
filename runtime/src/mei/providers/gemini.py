"""Google Gemini adapter (`streamGenerateContent?alt=sse`). The key goes in a header, never the URL."""

import re
from collections.abc import AsyncIterator
from urllib.parse import quote

import httpx

from .base import Done, ModelEvent, ModelRequest, ProviderError, TextDelta, ThinkingDelta, Usage
from .http_stream import error_message, first_int, loads, stream_post

_THOUGHT_SUMMARIES = re.compile(r"^gemini-(?:2\.5|3(?:\.|-))")


class GeminiProvider:
    def __init__(self, client: httpx.AsyncClient, *, label: str, base_url: str, model: str, api_key: str = "") -> None:
        if not model:
            raise ProviderError(f"{label}: no model selected")
        self.label = label
        self.model = model
        self._client = client
        self._url = f"{base_url.rstrip('/')}/models/{quote(model, safe='')}:streamGenerateContent?alt=sse"
        self._headers = {"x-goog-api-key": api_key} if api_key else {}

    def body(self, request: ModelRequest) -> dict:
        system = [{"text": t.content} for t in request.messages if t.role == "system"]
        body: dict = {"contents": [{"role": "model" if t.role == "assistant" else "user", "parts": [{"text": t.content}]}
                                   for t in request.messages if t.role != "system"]}
        if system:
            body["systemInstruction"] = {"parts": system}
        if _THOUGHT_SUMMARIES.search(self.model.lower()):
            body["generationConfig"] = {"thinkingConfig": {"includeThoughts": True}}
        return body

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        async for data in stream_post(self._client, self._url, self.body(request), self._headers, label=self.label):
            obj = loads(data)
            if obj is None:
                continue
            if obj.get("error"):
                raise ProviderError(f"{self.label}: {error_message(obj) or 'stream error'}")
            for candidate in obj.get("candidates") or []:
                parts = ((candidate or {}).get("content") or {}).get("parts") or []
                for part in parts:
                    if not isinstance(part, dict) or not isinstance(part.get("text"), str) or not part["text"]:
                        continue
                    yield ThinkingDelta(part["text"]) if part.get("thought") is True else TextDelta(part["text"])
            usage = obj.get("usageMetadata")
            if isinstance(usage, dict):
                yield Usage(first_int(usage, "promptTokenCount"), first_int(usage, "candidatesTokenCount"))
        yield Done("stop")
