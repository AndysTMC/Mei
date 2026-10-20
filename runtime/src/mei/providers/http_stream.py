"""Shared streaming POST for every adapter: one place for timeouts, size bounds, and error bodies."""

import json
from collections.abc import AsyncIterator
from typing import Literal

import httpx

from mei import obs

from .base import ProviderError
from .sse import SseDecoder

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_ERROR_BODY_BYTES = 64 * 1024
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 529})
TIMEOUT = httpx.Timeout(connect=15.0, read=60.0, write=30.0, pool=15.0)
_CREDENTIAL_HEADERS = frozenset({"authorization", "x-api-key", "x-goog-api-key", "api-key"})


async def stream_post(client: httpx.AsyncClient, url: str, body: dict, headers: dict[str, str], *,
                      label: str, framing: Literal["sse", "ndjson"] = "sse") -> AsyncIterator[str]:
    """POST `body` as JSON and yield each SSE `data:` payload (or NDJSON line) as text."""
    accept = "text/event-stream" if framing == "sse" else "application/x-ndjson"
    try:
        async with client.stream("POST", url, json=body, headers={"Accept": accept, **headers},
                                 timeout=TIMEOUT) as response:
            if response.status_code >= 400:
                raise await _http_error(label, response, headers)
            received = 0
            sse = SseDecoder()
            pending = b""
            async for chunk in response.aiter_bytes():
                received += len(chunk)
                if received > MAX_RESPONSE_BYTES:
                    raise ProviderError(f"{label}: response exceeded {MAX_RESPONSE_BYTES} bytes")
                if framing == "sse":
                    for event in sse.feed(chunk):
                        yield event.data
                else:
                    pending += chunk
                    *lines, pending = pending.split(b"\n")
                    for line in lines:
                        if line.strip():
                            yield line.decode("utf-8", "replace")
            if framing == "sse":
                for event in sse.close():
                    yield event.data
            elif pending.strip():
                yield pending.decode("utf-8", "replace")
    except httpx.TimeoutException as e:
        raise ProviderError(f"{label}: timed out ({type(e).__name__})", retryable=True) from None
    except httpx.TransportError as e:
        raise ProviderError(f"{label}: connection failed ({type(e).__name__})", retryable=True) from None


def scrub(text: str, headers: dict[str, str]) -> str:
    """Remove this request's own credentials from text the upstream sent back (some echo the key)."""
    return obs.scrub(text, credentials_in(headers))


def credentials_in(headers: dict[str, str]) -> list[str]:
    secrets = []
    for name, value in headers.items():
        if name.lower() in _CREDENTIAL_HEADERS and value:
            secrets.append(value.split(" ", 1)[1] if name.lower() == "authorization" and " " in value else value)
    return secrets


async def _http_error(label: str, response: httpx.Response, headers: dict[str, str]) -> ProviderError:
    body = b""
    async for chunk in response.aiter_bytes():
        body += chunk
        if len(body) >= MAX_ERROR_BODY_BYTES:
            break
    detail = scrub(error_message(body[:MAX_ERROR_BODY_BYTES]), headers)
    return ProviderError(f"{label}: HTTP {response.status_code}" + (f": {detail}" if detail else ""),
                         retryable=response.status_code in RETRYABLE_STATUS, status=response.status_code)


def error_message(body: bytes | str | dict) -> str:
    """Best-effort human message from the error shapes providers use."""
    data = body
    if isinstance(body, (bytes, str)):
        try:
            data = json.loads(body)
        except ValueError:
            text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
            return text.strip()[:300]
    if isinstance(data, list) and data:  # Gemini sometimes wraps errors in a list
        data = data[0]
    if isinstance(data, dict):
        err = data.get("error")
        if isinstance(err, dict) and isinstance(err.get("message"), str):
            return err["message"][:300]
        if isinstance(err, str):
            return err[:300]
        if isinstance(data.get("message"), str):
            return data["message"][:300]
    return ""


def loads(data: str) -> dict | None:
    try:
        value = json.loads(data)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def as_int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def first_int(record: dict, *keys: str) -> int | None:
    for key in keys:
        value = as_int(record.get(key))
        if value is not None:
            return value
    return None
