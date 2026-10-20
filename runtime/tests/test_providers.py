"""Adapters, profiles, and the factory, against recorded wire formats (no network)."""

import json

import httpx
import pytest

from mei.protocol import ProviderConfig
from mei.providers import factory
from mei.providers.anthropic import AnthropicProvider
from mei.providers.base import ChatTurn, Done, ModelRequest, ProviderError, TextDelta, ThinkingDelta, Usage
from mei.providers.gemini import GeminiProvider
from mei.providers.ollama import OllamaProvider
from mei.providers.openai_chat import OpenAIChatProvider
from mei.providers.openai_normalize import StreamNormalizer, separate_glued_reasoning_blocks
from mei.providers.profiles import PROFILES, opencode_api_mode, resolve, resolve_id
from mei.providers.responses import ResponsesProvider

REQ = ModelRequest([ChatTurn("system", "be brief"), ChatTurn("user", "hi"), ChatTurn("assistant", "hello"),
                    ChatTurn("user", "again")])


class Chunks(httpx.AsyncByteStream):
    def __init__(self, data: bytes, size: int = 7) -> None:
        self._parts = [data[i:i + size] for i in range(0, len(data), size)]

    async def __aiter__(self):
        for p in self._parts:
            yield p


def sse(*objs) -> bytes:
    return b"".join(b"data: " + (o if isinstance(o, bytes) else json.dumps(o).encode()) + b"\n\n" for o in objs)


def mock(body: bytes, status: int = 200, seen: list | None = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, stream=Chunks(body))
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def collect(provider) -> list:
    return [e async for e in provider.stream(REQ)]


def text(events) -> str:
    return "".join(e.text for e in events if isinstance(e, TextDelta))


def thinking(events) -> str:
    return "".join(e.text for e in events if isinstance(e, ThinkingDelta))


# ── Stream normalizer (ported one-for-one from tests/openaiResponse.test.ts) ──


def run(chunks: list[dict]) -> tuple[str, str]:
    n = StreamNormalizer()
    out = [n.consume(c) for c in chunks] + [n.flush()]
    return "".join(t for t, _ in out), "".join(r for _, r in out)


def delta(**d) -> dict:
    return {"choices": [{"delta": d}]}


def test_split_inline_reasoning_tags():
    assert run([delta(content="<thi"), delta(content="nk>private"), delta(content="</think>\nVisible")]) == \
        ("\nVisible", "private")


def test_literal_tag_mentions_stay_visible_and_partial_prose_flushes():
    assert run([delta(content="Use <think> tags and x <")]) == ("Use <think> tags and x <", "")


def test_bounded_pair_mid_sentence():
    n = StreamNormalizer()
    assert n.consume(delta(content="Before <reasoning>private</reasoning> after")) == ("Before  after", "private")


def test_typed_blocks_and_reasoning_details():
    n = StreamNormalizer()
    out = n.consume(delta(content=[None, {"type": "thinking", "text": "typed thought"},
                                   {"type": "output_text", "output_text": "answer"}],
                          reasoning_details=[{"summary": "summary thought"}, None]))
    assert out == ("answer", "summary thought\n\ntyped thought")


def test_split_closing_tag_and_reset_after_unclosed_block():
    assert run([delta(content="<reasoning>private</reas"), delta(content="oning>visible")]) == ("visible", "private")
    n = StreamNormalizer()
    assert n.consume(delta(content="<think>private")) == ("", "private")
    assert n.flush() == ("", "")
    assert n.consume(delta(content="answer")) == ("answer", "")


def test_glued_summary_blocks_get_a_paragraph_break():
    n = StreamNormalizer()
    assert n.consume(delta(reasoning_content="**First**body"))[1] == "**First**body"
    assert n.consume(delta(reasoning_content="**Second**body"))[1] == "\n\n**Second**body"
    assert separate_glued_reasoning_blocks("token ", "**fragment") == "**fragment"


def test_whitespace_only_reasoning_deltas_survive():
    assert run([delta(reasoning_content=r) for r in ("first", " ", "second")])[1] == "first second"


def test_legacy_text_field():
    assert run([{"choices": [{"text": "legacy"}]}]) == ("legacy", "")


# ── OpenAI-compatible chat ───────────────────────────────────────────────────


async def test_openai_chat_think_tags_split_across_network_chunks():
    body = sse(delta(content="<think>plan"), delta(content=" more</think>"), delta(content="Answer"),
               {"choices": [], "usage": {"prompt_tokens": 0, "completion_tokens": 4}}, b"[DONE]")
    seen: list = []
    p = OpenAIChatProvider(mock(body, seen=seen), label="T", url="https://x.test/v1/chat/completions", model="m",
                           api_key="k123", headers={"X-Title": "Mei"}, extra_body={"reasoning_effort": "high"})
    events = await collect(p)
    assert (text(events), thinking(events)) == ("Answer", "plan more")
    assert Usage(0, 4) in events and events[-1] == Done("stop")
    sent = json.loads(seen[0].content)
    assert sent["reasoning_effort"] == "high" and sent["messages"][0] == {"role": "system", "content": "be brief"}
    assert seen[0].headers["authorization"] == "Bearer k123"


async def test_openai_chat_stream_error():
    p = OpenAIChatProvider(mock(sse({"error": {"message": "model unloaded"}})), label="T",
                           url="https://x.test/v1/chat/completions", model="m")
    with pytest.raises(ProviderError, match="model unloaded"):
        await collect(p)


# ── Anthropic ────────────────────────────────────────────────────────────────

ANTHROPIC_STREAM = sse(
    {"type": "message_start", "message": {"usage": {"input_tokens": 12}}},
    {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Let me see."}},
    {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Hi "}},
    {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "there"}},
    {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 5}},
    {"type": "message_stop"},
)


async def test_anthropic_stream_auth_and_body():
    seen: list = []
    p = AnthropicProvider(mock(ANTHROPIC_STREAM, seen=seen), label="Anthropic", url="https://api.anthropic.test/v1/messages",
                          model="claude-sonnet-4-6", api_key="sk-ant")
    events = await collect(p)
    assert (text(events), thinking(events)) == ("Hi there", "Let me see.")
    assert Usage(12, 5) in events
    req = seen[0]
    assert req.headers["x-api-key"] == "sk-ant" and "authorization" not in req.headers
    assert req.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(req.content)
    assert body["system"] == "be brief" and [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert body["thinking"] == {"type": "adaptive", "display": "summarized"} and body["max_tokens"] == 4096


async def test_anthropic_bearer_auth_for_opencode_and_no_thinking_on_older_models():
    seen: list = []
    p = AnthropicProvider(mock(ANTHROPIC_STREAM, seen=seen), label="OpenCode", url="https://opencode.test/messages",
                          model="qwen3-coder", api_key="k", bearer_auth=True)
    await collect(p)
    assert seen[0].headers["authorization"] == "Bearer k" and "x-api-key" not in seen[0].headers
    assert "thinking" not in json.loads(seen[0].content)


async def test_anthropic_error_event():
    p = AnthropicProvider(mock(sse({"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})),
                          label="Anthropic", url="https://a.test", model="m")
    with pytest.raises(ProviderError, match="Overloaded") as err:
        await collect(p)
    assert err.value.retryable


# ── Gemini ───────────────────────────────────────────────────────────────────


async def test_gemini_stream_thoughts_usage_and_key_in_header():
    body = sse({"candidates": [{"content": {"parts": [{"text": "pondering", "thought": True}]}}]},
               {"candidates": [{"content": {"parts": [{"text": "Hello "}]}}]},
               {"candidates": [{"content": {"parts": [{"text": "world"}]}}],
                "usageMetadata": {"promptTokenCount": 9, "candidatesTokenCount": 2}})
    seen: list = []
    p = GeminiProvider(mock(body, seen=seen), label="Gemini", base_url="https://g.test/v1beta/",
                       model="gemini-2.5-flash", api_key="AIzaSecret")
    events = await collect(p)
    assert (text(events), thinking(events)) == ("Hello world", "pondering")
    assert Usage(9, 2) in events
    req = seen[0]
    assert str(req.url) == "https://g.test/v1beta/models/gemini-2.5-flash:streamGenerateContent?alt=sse"
    assert req.headers["x-goog-api-key"] == "AIzaSecret" and "AIza" not in str(req.url)
    sent = json.loads(req.content)
    assert sent["systemInstruction"] == {"parts": [{"text": "be brief"}]}
    assert [c["role"] for c in sent["contents"]] == ["user", "model", "user"]
    assert sent["generationConfig"]["thinkingConfig"]["includeThoughts"] is True


async def test_gemini_model_ids_cannot_change_the_url_path():
    seen: list = []
    p = GeminiProvider(mock(sse({}), seen=seen), label="Gemini", base_url="https://g.test/v1beta",
                       model="../evil?x=1#y")
    await collect(p)
    url = seen[0].url
    assert url.raw_path == b"/v1beta/models/..%2Fevil%3Fx%3D1%23y:streamGenerateContent?alt=sse"
    assert dict(url.params) == {"alt": "sse"} and url.host == "g.test" and not url.fragment


async def test_gemini_error_object():
    p = GeminiProvider(mock(sse({"error": {"code": 429, "message": "Resource exhausted"}})), label="Gemini",
                       base_url="https://g.test", model="m")
    with pytest.raises(ProviderError, match="Resource exhausted"):
        await collect(p)


# ── Ollama ───────────────────────────────────────────────────────────────────


async def test_ollama_ndjson_thinking_and_done():
    lines = [{"message": {"role": "assistant", "thinking": "hmm"}},
             {"message": {"role": "assistant", "content": "Hi"}},
             {"message": {"role": "assistant", "content": "!"}, "done": True, "prompt_eval_count": 7, "eval_count": 2}]
    body = b"".join(json.dumps(line).encode() + b"\n" for line in lines)
    seen: list = []
    p = OllamaProvider(mock(body, seen=seen), label="Ollama", url="http://127.0.0.1:11434/api/chat", model="qwen3")
    events = await collect(p)
    assert (text(events), thinking(events)) == ("Hi!", "hmm") and Usage(7, 2) in events
    sent = json.loads(seen[0].content)
    assert sent["think"] is True and sent["stream"] is True


async def test_ollama_error_line_and_gpt_oss_think_level():
    seen: list = []
    p = OllamaProvider(mock(b'{"error":"model not found"}\n', seen=seen), label="Ollama", url="http://o.test/api/chat",
                       model="gpt-oss:20b")
    with pytest.raises(ProviderError, match="model not found"):
        await collect(p)
    assert json.loads(seen[0].content)["think"] == "medium"


# ── Responses ────────────────────────────────────────────────────────────────


async def test_responses_stream_store_false_and_developer_role():
    body = sse({"type": "response.reasoning_summary_text.delta", "delta": "thinking…"},
               {"type": "response.output_text.delta", "delta": "Answer"},
               {"type": "response.completed", "response": {"usage": {"input_tokens": 3, "output_tokens": 1}}})
    seen: list = []
    p = ResponsesProvider(mock(body, seen=seen), label="OpenCode", url="https://o.test/responses", model="gpt-5", api_key="k")
    events = await collect(p)
    assert (text(events), thinking(events)) == ("Answer", "thinking…") and Usage(3, 1) in events
    sent = json.loads(seen[0].content)
    assert sent["store"] is False and sent["input"][0]["role"] == "developer"


async def test_responses_failed_and_incomplete():
    p = ResponsesProvider(mock(sse({"type": "response.failed", "response": {"error": {"message": "quota"}}})),
                          label="O", url="https://o.test", model="m")
    with pytest.raises(ProviderError, match="quota"):
        await collect(p)
    p = ResponsesProvider(mock(sse({"type": "response.output_text.delta", "delta": "Partial"},
                                   {"type": "response.incomplete", "response": {"incomplete_details": {"reason": "max_output_tokens"}}})),
                          label="O", url="https://o.test", model="m")
    assert text(await collect(p)) == "Partial\n\n[Response incomplete: max_output_tokens.]"
    p = ResponsesProvider(mock(sse({"type": "response.incomplete", "response": {"incomplete_details": {"reason": "content_filter"}}})),
                          label="O", url="https://o.test", model="m")
    with pytest.raises(ProviderError, match="content_filter"):
        await collect(p)


# ── Profiles and factory ─────────────────────────────────────────────────────


def test_profiles_match_the_extension_ids():
    assert set(PROFILES) == {"ollama", "llamacpp", "lmstudio", "openai", "anthropic", "gemini", "groq", "mistral",
                             "openrouter", "deepseek", "fireworks", "nvidia", "opencode", "githubcopilot", "custom"}
    assert resolve_id("OR") == "openrouter" and resolve_id("vllm") == "custom" and resolve_id("nope") is None


@pytest.mark.parametrize("model,mode,api_mode,path", [
    ("glm-5.3", "go", "chat_completions", "/zen/go/v1/chat/completions"),
    ("opencode-go/qwen3.8-max", "go", "anthropic_messages", "/zen/go/v1/messages"),
    ("minimax-m3", "go", "anthropic_messages", "/zen/go/v1/messages"),
    ("claude-sonnet-4-6", "zen", "anthropic_messages", "/zen/v1/messages"),
    ("gpt-5.6-luna", "zen", "responses", "/zen/v1/responses"),
    ("big-pickle", "zen", "chat_completions", "/zen/v1/chat/completions"),
])
def test_opencode_routing(model, mode, api_mode, path):
    r = resolve("opencode", model=model, mode=mode)
    assert opencode_api_mode(model, mode) == api_mode == r.api_mode
    assert r.url == "https://opencode.ai" + path and "/" not in r.model


def test_url_override():
    assert resolve("lmstudio", model="m", url=" http://127.0.0.1:9/v1/chat/completions ").url == \
        "http://127.0.0.1:9/v1/chat/completions"


@pytest.mark.parametrize("provider_id,model,cls", [
    ("gemini", "gemini-flash-lite-latest", GeminiProvider), ("anthropic", "claude-x", AnthropicProvider),
    ("ollama", "qwen3", OllamaProvider), ("openrouter", "a/b", OpenAIChatProvider),
    ("llamacpp", "x", OpenAIChatProvider), ("opencode", "gpt-5", ResponsesProvider),
    ("opencode", "qwen3-max", AnthropicProvider), ("deepseek", "deepseek-v4", OpenAIChatProvider),
])
async def test_factory_picks_the_adapter(provider_id, model, cls):
    asked: list[str] = []

    async def key_for(pid):
        asked.append(pid)
        return "k"

    p = await factory.build(ProviderConfig(id=provider_id, model=model, mode="go"), httpx.AsyncClient(), key_for)
    assert isinstance(p, cls) and asked == [provider_id]


async def test_factory_refuses_retired_and_unknown_providers():
    async def key_for(_pid):
        return ""
    for cfg in (ProviderConfig(id="githubcopilot", model="x"), ProviderConfig(id="")):
        with pytest.raises(ProviderError):
            await factory.build(cfg, httpx.AsyncClient(), key_for)


def test_deepseek_body():
    assert factory.deepseek_body("deepseek-v4-pro", "enabled", "max") == {"thinking": {"type": "enabled"}, "reasoning_effort": "max"}
    assert factory.deepseek_body("deepseek-v4", "enabled", "weird") == {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}
    assert factory.deepseek_body("deepseek-v4", "disabled", "") == {"thinking": {"type": "disabled"}}
    assert factory.deepseek_body("deepseek-v3.2", "enabled", "max") == {}
    assert factory.deepseek_body("deepseek-v4", "", "max") == {}
