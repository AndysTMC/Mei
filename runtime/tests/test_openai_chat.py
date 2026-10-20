import json

import httpx
import pytest

from mei.providers.base import ChatTurn, Done, ModelRequest, ProviderError, TextDelta, ThinkingDelta, Usage
from mei.providers.openai_chat import MAX_RESPONSE_BYTES, OpenAIChatProvider

URL = "https://api.example.test/v1/chat/completions"
REQUEST = ModelRequest([ChatTurn("user", "hi")])


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self):
        for c in self._chunks:
            yield c


def sse(*objs) -> bytes:
    return b"".join(b"data: " + (o if isinstance(o, bytes) else json.dumps(o).encode()) + b"\n\n" for o in objs)


def provider(handler, key="sk-test-1234567890") -> tuple[OpenAIChatProvider, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    return OpenAIChatProvider(client, label="Test", url=URL, model="m1", api_key=key,
                              headers={"X-Title": "Mei"}), seen


async def collect(p) -> list:
    return [e async for e in p.stream(REQUEST)]


def ok(*chunks: bytes) -> httpx.Response:
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Chunks(list(chunks)))


async def test_streams_text_thinking_usage_and_sends_auth():
    body = sse({"choices": [{"delta": {"reasoning_content": "hmm"}}]},
               {"choices": [{"delta": {"content": "Hel"}}]},
               {"choices": [{"delta": {"content": [{"type": "text", "text": "lo"}]}}]},
               {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}, b"[DONE]")
    p, seen = provider(lambda r: ok(body[:7], body[7:31], body[31:]))
    events = await collect(p)
    assert events == [ThinkingDelta("hmm"), TextDelta("Hel"), TextDelta("lo"), Usage(3, 2), Done("stop")]
    req = seen[0]
    assert req.headers["authorization"] == "Bearer sk-test-1234567890"
    assert req.headers["x-title"] == "Mei"
    assert json.loads(req.content) == {"model": "m1", "stream": True, "messages": [{"role": "user", "content": "hi"}]}


async def test_no_auth_header_without_a_key():
    p, seen = provider(lambda r: ok(sse(b"[DONE]")), key="")
    await collect(p)
    assert "authorization" not in seen[0].headers


async def test_stream_error_frame_raises():
    p, _ = provider(lambda r: ok(sse({"choices": [{"delta": {"content": "a"}}]}, {"error": {"message": "model unloaded"}})))
    with pytest.raises(ProviderError, match="model unloaded"):
        await collect(p)


@pytest.mark.parametrize("status,retryable", [(429, True), (503, True), (401, False), (400, False)])
async def test_http_errors(status, retryable):
    p, _ = provider(lambda r: httpx.Response(status, json={"error": {"message": "nope"}}))
    with pytest.raises(ProviderError) as err:
        await collect(p)
    assert err.value.status == status and err.value.retryable is retryable
    assert "nope" in str(err.value) and "sk-test" not in str(err.value)


async def test_oversized_response_is_cut_off():
    big = sse({"choices": [{"delta": {"content": "x" * 1024}}]}) * (MAX_RESPONSE_BYTES // 1024 + 10)
    p, _ = provider(lambda r: ok(big))
    with pytest.raises(ProviderError, match="exceeded"):
        await collect(p)


async def test_connection_failure_is_retryable():
    def boom(request):
        raise httpx.ConnectError("refused", request=request)

    p, _ = provider(boom)
    with pytest.raises(ProviderError) as err:
        await collect(p)
    assert err.value.retryable


def test_rejects_non_http_urls():
    with pytest.raises(ProviderError):
        OpenAIChatProvider(httpx.AsyncClient(), label="T", url="file:///etc/passwd", model="m")
