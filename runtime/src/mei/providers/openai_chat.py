"""OpenAI-compatible Chat Completions adapter (streaming).

Serves OpenAI, Groq, Mistral, OpenRouter, DeepSeek, Fireworks, NVIDIA, OpenCode (chat models),
llama.cpp, LM Studio, and custom URLs. Reasoning is separated from the answer by
`StreamNormalizer`, whatever shape the provider uses.
"""

from collections.abc import AsyncIterator

import httpx

from .base import ChatTurn, Done, ModelEvent, ModelRequest, ProviderError, TextDelta, ThinkingDelta, Usage
from .http_stream import MAX_RESPONSE_BYTES, error_message, first_int, loads, stream_post
from .openai_normalize import StreamNormalizer

__all__ = ["OpenAIChatProvider", "MAX_RESPONSE_BYTES", "to_turns"]


class OpenAIChatProvider:
    def __init__(self, client: httpx.AsyncClient, *, label: str, url: str, model: str,
                 api_key: str = "", headers: dict[str, str] | None = None, extra_body: dict | None = None) -> None:
        if not url.startswith(("https://", "http://")):
            raise ProviderError(f"{label}: endpoint must be an http(s) URL")
        if not model:
            raise ProviderError(f"{label}: no model selected")
        self.label = label
        self.model = model
        self._client = client
        self._url = url
        self._headers = {**(headers or {}), **({"Authorization": f"Bearer {api_key}"} if api_key else {})}
        self._extra = dict(extra_body or {})

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        body = {"model": self.model, "stream": True,
                "messages": [{"role": t.role, "content": t.content} for t in request.messages], **self._extra}
        normalizer = StreamNormalizer()
        async for data in stream_post(self._client, self._url, body, self._headers, label=self.label):
            if data.strip() == "[DONE]":
                break
            obj = loads(data)
            if obj is None:
                continue
            if obj.get("error"):
                raise ProviderError(f"{self.label}: {error_message(obj) or 'stream error'}")
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
        yield Done("stop")


def to_turns(messages: list[dict]) -> list[ChatTurn]:
    return [ChatTurn(m["role"], m["content"]) for m in messages if m["role"] in ("system", "user", "assistant")]
