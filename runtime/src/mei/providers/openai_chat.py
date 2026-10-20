"""OpenAI-compatible Chat Completions adapter (streaming).

Covers the providers whose Mei profile uses the `openai` transport with `chat_completions`:
OpenAI, Groq, Mistral, OpenRouter, DeepSeek, Fireworks, NVIDIA, LM Studio, and custom URLs.
"""

import json
from collections.abc import AsyncIterator

import httpx

from .base import ChatTurn, Done, ModelEvent, ModelRequest, ProviderError, TextDelta, ThinkingDelta, Usage
from .sse import SseDecoder

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ERROR_BODY_BYTES = 64 * 1024
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
TIMEOUT = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=15.0)


class OpenAIChatProvider:
    def __init__(self, client: httpx.AsyncClient, *, label: str, url: str, model: str,
                 api_key: str = "", headers: dict[str, str] | None = None) -> None:
        if not url.startswith(("https://", "http://")):
            raise ProviderError(f"{label}: endpoint must be an http(s) URL")
        if not model:
            raise ProviderError(f"{label}: no model selected")
        self.label = label
        self.model = model
        self._client = client
        self._url = url
        self._api_key = api_key
        self._headers = dict(headers or {})

    def _body(self, request: ModelRequest) -> dict:
        return {"model": self.model, "stream": True,
                "messages": [{"role": t.role, "content": t.content} for t in request.messages]}

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        headers = {"Accept": "text/event-stream", **self._headers}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            async with self._client.stream("POST", self._url, json=self._body(request), headers=headers,
                                           timeout=TIMEOUT) as response:
                if response.status_code >= 400:
                    raise await _http_error(self.label, response)
                decoder = SseDecoder()
                received = 0
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > MAX_RESPONSE_BYTES:
                        raise ProviderError(f"{self.label}: response exceeded {MAX_RESPONSE_BYTES} bytes")
                    for event in decoder.feed(chunk):
                        for item in _parse(self.label, event.data):
                            yield item
                            if isinstance(item, Done):
                                return
                for event in decoder.close():
                    for item in _parse(self.label, event.data):
                        yield item
                yield Done("eof")
        except httpx.TimeoutException as e:
            raise ProviderError(f"{self.label}: timed out ({type(e).__name__})", retryable=True) from None
        except httpx.TransportError as e:
            raise ProviderError(f"{self.label}: connection failed ({type(e).__name__})", retryable=True) from None


async def _http_error(label: str, response: httpx.Response) -> ProviderError:
    body = b""
    async for chunk in response.aiter_bytes():
        body += chunk
        if len(body) >= MAX_ERROR_BODY_BYTES:
            break
    detail = _error_message(body[:MAX_ERROR_BODY_BYTES])
    message = f"{label}: HTTP {response.status_code}" + (f": {detail}" if detail else "")
    return ProviderError(message, retryable=response.status_code in RETRYABLE_STATUS, status=response.status_code)


def _error_message(body: bytes) -> str:
    try:
        data = json.loads(body)
    except ValueError:
        return body.decode("utf-8", "replace").strip()[:300]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and isinstance(err.get("message"), str):
            return err["message"][:300]
        if isinstance(err, str):
            return err[:300]
        if isinstance(data.get("message"), str):
            return data["message"][:300]
    return ""


def _parse(label: str, data: str) -> list[ModelEvent]:
    if data.strip() == "[DONE]":
        return [Done("stop")]
    try:
        obj = json.loads(data)
    except ValueError:
        return []
    if not isinstance(obj, dict):
        return []
    if obj.get("error"):
        raise ProviderError(f"{label}: {_error_message(json.dumps(obj).encode()) or 'stream error'}")
    out: list[ModelEvent] = []
    usage = obj.get("usage")
    if isinstance(usage, dict):
        out.append(Usage(input_tokens=_int(usage.get("prompt_tokens")),
                         output_tokens=_int(usage.get("completion_tokens"))))
    for choice in obj.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta") or choice.get("message") or {}
        thinking = delta.get("reasoning_content") or delta.get("reasoning")
        if isinstance(thinking, str) and thinking:
            out.append(ThinkingDelta(thinking))
        text = _content_text(delta.get("content"))
        if text:
            out.append(TextDelta(text))
    return out


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # typed parts, e.g. Mistral: [{"type": "text", "text": "…"}]
        return "".join(p.get("text", "") for p in content
                       if isinstance(p, dict) and p.get("type") in ("text", "output_text") and isinstance(p.get("text"), str))
    return ""


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def to_turns(messages: list[dict]) -> list[ChatTurn]:
    return [ChatTurn(m["role"], m["content"]) for m in messages if m["role"] in ("system", "user", "assistant")]
