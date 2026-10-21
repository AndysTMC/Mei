"""Tool calling on every wire format: how tools, calls, and results are sent, and how streamed calls
are assembled (recorded shapes, no network)."""

import json

from mei.providers.anthropic import AnthropicProvider
from mei.providers.base import (ChatTurn, Done, ModelRequest, Replay, ReplayData, ToolCall, ToolCalled, ToolSpec,
                                tool_groups)
from mei.providers.fake import FakeProvider
from mei.providers.gemini import GeminiProvider
from mei.providers.ollama import OllamaProvider
from mei.providers.openai_chat import OpenAIChatProvider, merge_reasoning_details

from test_providers import delta, mock, sse

TOOLS = (ToolSpec("fs_list", "List a folder.", {"type": "object", "properties": {"path": {"type": "string"}},
                                                "required": ["path"]}),)
CALL = ToolCall("call_1", "fs_list", '{"path": "~/Downloads"}', signature="sig-1")
HISTORY = ModelRequest([
    ChatTurn("system", "rules"),
    ChatTurn("user", "find invoices"),
    ChatTurn("assistant", "Looking.", tool_calls=(CALL, ToolCall("call_2", "fs_list", '{"path": "~/Documents"}')),
             replay=Replay("anthropic", {"blocks": [{"type": "thinking", "thinking": "hm", "signature": "s"}]})),
    ChatTurn("tool", "a.pdf", tool_call_id="call_1", name="fs_list"),
    ChatTurn("tool", "denied", tool_call_id="call_2", name="fs_list", is_error=True),
    ChatTurn("user", "only PDFs"),
], tools=TOOLS)


async def run(provider, request=HISTORY) -> list:
    return [e async for e in provider.stream(request)]


def calls(events) -> list[ToolCall]:
    return [e.call for e in events if isinstance(e, ToolCalled)]


def test_tool_groups_gather_consecutive_results():
    groups = tool_groups(HISTORY.messages)
    assert [g.role if isinstance(g, ChatTurn) else [t.tool_call_id for t in g] for g in groups] == \
        ["system", "user", "assistant", ["call_1", "call_2"], "user"]


# ── OpenAI-compatible ────────────────────────────────────────────────────────


async def test_openai_chat_sends_tools_calls_and_results():
    seen: list = []
    p = OpenAIChatProvider(mock(sse(delta(content="ok"), b"[DONE]"), seen=seen), label="T",
                           url="https://x.test/v1/chat/completions", model="m")
    await run(p)
    body = json.loads(seen[0].content)
    assert body["tools"] == [{"type": "function", "function": {"name": "fs_list", "description": "List a folder.",
                                                               "parameters": TOOLS[0].parameters}}]
    assistant = body["messages"][2]
    assert assistant["content"] == "Looking." and assistant["tool_calls"][0] == {
        "id": "call_1", "type": "function", "function": {"name": "fs_list", "arguments": '{"path": "~/Downloads"}'}}
    assert "reasoning_content" not in assistant and "reasoning_details" not in assistant  # Anthropic's replay stays out
    assert body["messages"][3:5] == [{"role": "tool", "tool_call_id": "call_1", "content": "a.pdf"},
                                     {"role": "tool", "tool_call_id": "call_2", "content": "denied"}]


async def test_openai_chat_assembles_streamed_call_fragments():
    body = sse(
        delta(content="Let me look."),
        delta(tool_calls=[{"index": 0, "id": "call_a", "type": "function", "function": {"name": "fs_list", "arguments": ""}}]),
        delta(tool_calls=[{"index": 0, "function": {"arguments": '{"pa'}}]),
        delta(tool_calls=[{"index": 1, "id": "call_b", "function": {"name": "fs_read_text", "arguments": "{}"}}]),
        delta(tool_calls=[{"index": 0, "function": {"arguments": 'th": "~"}'}}]),
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}, b"[DONE]")
    events = await run(OpenAIChatProvider(mock(body), label="T", url="https://x.test/v1/chat/completions", model="m"))
    assert calls(events) == [ToolCall("call_a", "fs_list", '{"path": "~"}'), ToolCall("call_b", "fs_read_text", "{}")]
    assert events[-1] == Done("tool_calls")


async def test_openai_chat_whole_calls_without_index_or_id():
    body = sse(delta(tool_calls=[{"function": {"name": "a", "arguments": {"x": 1}}},
                                 {"function": {"name": "b", "arguments": "{}"}}]), b"[DONE]")
    events = await run(OpenAIChatProvider(mock(body), label="T", url="https://x.test/v1/chat/completions", model="m"))
    assert calls(events) == [ToolCall("call_1", "a", '{"x": 1}'), ToolCall("call_2", "b", "{}")]


async def test_deepseek_reasoning_and_openrouter_details_round_trip():
    body = sse(delta(reasoning_content="think "), delta(reasoning_content="more"),
               delta(reasoning_details=[{"type": "reasoning.text", "text": "r1", "index": 0}]),
               delta(reasoning_details=[{"type": "reasoning.text", "text": "r2", "signature": "SIG", "index": 0}]),
               delta(tool_calls=[{"index": 0, "id": "c", "function": {"name": "fs_list", "arguments": "{}"}}]),
               b"[DONE]")
    p = OpenAIChatProvider(mock(body), label="T", url="https://x.test/v1/chat/completions", model="m", echo_reasoning=True)
    events = await run(p)
    replay = next(e.replay for e in events if isinstance(e, ReplayData))
    assert replay.format == "openai_chat" and replay.data["reasoning_content"] == "think more"
    assert replay.data["reasoning_details"] == [{"type": "reasoning.text", "text": "r1r2", "signature": "SIG", "index": 0}]
    turn = ChatTurn("assistant", "", tool_calls=(ToolCall("c", "fs_list", "{}"),), replay=replay)
    sent = p._message(turn)
    assert sent["reasoning_content"] == "think more" and sent["reasoning_details"][0]["signature"] == "SIG"
    assert sent["content"] is None
    quiet = OpenAIChatProvider(mock(b""), label="T", url="https://x.test", model="m")
    assert "reasoning_content" not in quiet._message(turn)  # only DeepSeek wants it back


def test_merge_reasoning_details_without_index():
    acc: list[dict] = []
    merge_reasoning_details(acc, [{"type": "reasoning.text", "text": "a"}])
    merge_reasoning_details(acc, [{"type": "reasoning.text", "text": "b"}])
    assert acc == [{"type": "reasoning.text", "text": "ab", "index": 0}]


async def test_no_replay_for_plain_answers():
    body = sse(delta(reasoning_details=[{"type": "reasoning.text", "text": "r"}]), delta(content="hi"), b"[DONE]")
    events = await run(OpenAIChatProvider(mock(body), label="T", url="https://x.test", model="m"))
    assert not any(isinstance(e, ReplayData) for e in events) and events[-1] == Done("stop")


# ── Anthropic ────────────────────────────────────────────────────────────────


async def test_anthropic_sends_thinking_tool_use_and_grouped_results():
    seen: list = []
    p = AnthropicProvider(mock(sse({"type": "message_stop"}), seen=seen), label="A", url="https://a.test", model="m")
    await run(p)
    body = json.loads(seen[0].content)
    assert body["tools"] == [{"name": "fs_list", "description": "List a folder.", "input_schema": TOOLS[0].parameters}]
    assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
    assert body["messages"][1]["content"] == [
        {"type": "thinking", "thinking": "hm", "signature": "s"},
        {"type": "text", "text": "Looking."},
        {"type": "tool_use", "id": "call_1", "name": "fs_list", "input": {"path": "~/Downloads"}},
        {"type": "tool_use", "id": "call_2", "name": "fs_list", "input": {"path": "~/Documents"}}]
    assert body["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "call_1", "content": "a.pdf"},
        {"type": "tool_result", "tool_use_id": "call_2", "content": "denied", "is_error": True},
        {"type": "text", "text": "only PDFs"}]


async def test_anthropic_assembles_tool_use_and_keeps_signed_thinking():
    body = sse(
        {"type": "message_start", "message": {"usage": {"input_tokens": 3}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "plan"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "SIG"}},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "redacted_thinking", "data": "XYZ"}},
        {"type": "content_block_start", "index": 2, "content_block": {"type": "tool_use", "id": "toolu_1", "name": "fs_list", "input": {}}},
        {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": '{"path":'}},
        {"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": ' "~"}'}},
        {"type": "content_block_stop", "index": 2},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 9}},
        {"type": "message_stop"})
    events = await run(AnthropicProvider(mock(body), label="A", url="https://a.test", model="m"))
    assert calls(events) == [ToolCall("toolu_1", "fs_list", '{"path": "~"}')]
    replay = next(e.replay for e in events if isinstance(e, ReplayData))
    assert replay == Replay("anthropic", {"blocks": [{"type": "thinking", "thinking": "plan", "signature": "SIG"},
                                                     {"type": "redacted_thinking", "data": "XYZ"}]})
    assert events[-1] == Done("tool_calls")


# ── Gemini ───────────────────────────────────────────────────────────────────


async def test_gemini_sends_declarations_signatures_and_responses():
    seen: list = []
    p = GeminiProvider(mock(sse({"candidates": [{"finishReason": "STOP"}]}), seen=seen), label="G",
                       base_url="https://g.test", model="gemini-3-flash")
    await run(p)
    body = json.loads(seen[0].content)
    assert body["tools"] == [{"functionDeclarations": [{"name": "fs_list", "description": "List a folder.",
                                                        "parameters": TOOLS[0].parameters}]}]
    model_turn = body["contents"][1]
    assert model_turn["role"] == "model" and model_turn["parts"] == [
        {"text": "Looking."},
        {"functionCall": {"name": "fs_list", "args": {"path": "~/Downloads"}}, "thoughtSignature": "sig-1"},
        {"functionCall": {"name": "fs_list", "args": {"path": "~/Documents"}}}]
    assert body["contents"][2] == {"role": "user", "parts": [
        {"functionResponse": {"name": "fs_list", "response": {"result": "a.pdf"}}},
        {"functionResponse": {"name": "fs_list", "response": {"error": "denied"}}},
        {"text": "only PDFs"}]}


async def test_gemini_reads_function_calls_with_signatures():
    body = sse({"candidates": [{"content": {"parts": [
        {"text": "Checking."},
        {"functionCall": {"name": "fs_list", "args": {"path": "~"}}, "thoughtSignature": "SIG"},
        {"functionCall": {"name": "apps_list", "args": {}}}]}, "finishReason": "STOP"}]})
    events = await run(GeminiProvider(mock(body), label="G", base_url="https://g.test", model="m"))
    assert calls(events) == [ToolCall("call_1", "fs_list", '{"path": "~"}', signature="SIG"),
                             ToolCall("call_2", "apps_list", "{}")]
    assert events[-1] == Done("tool_calls")


# ── Ollama ───────────────────────────────────────────────────────────────────


async def test_ollama_tools_calls_and_named_results():
    seen: list = []
    stream = (b'{"message":{"content":"","tool_calls":[{"function":{"name":"fs_list","arguments":{"path":"~"}}}]},"done":false}\n'
              b'{"message":{"content":""},"done":true,"prompt_eval_count":5,"eval_count":2}\n')
    events = await run(OllamaProvider(mock(stream, seen=seen), label="O", url="http://o.test/api/chat", model="qwen3"))
    assert calls(events) == [ToolCall("call_1", "fs_list", '{"path": "~"}')] and events[-1] == Done("tool_calls")
    body = json.loads(seen[0].content)
    assert body["tools"][0]["function"]["name"] == "fs_list"
    assert body["messages"][2]["tool_calls"] == [{"function": {"name": "fs_list", "arguments": {"path": "~/Downloads"}}},
                                                 {"function": {"name": "fs_list", "arguments": {"path": "~/Documents"}}}]
    assert body["messages"][3] == {"role": "tool", "content": "a.pdf", "tool_name": "fs_list"}


# ── Fake ─────────────────────────────────────────────────────────────────────


async def test_fake_script_moves_one_step_per_round_trip(tmp_path):
    log = tmp_path / "calls.jsonl"
    p = FakeProvider({"delay_ms": 0, "call_log": str(log), "script": [
        {"text": "Looking.", "tool_calls": [{"name": "fs_list", "arguments": {"path": "~"}}]},
        {"text": "Done."}]})
    first = await run(p, ModelRequest([ChatTurn("user", "go")], tools=TOOLS))
    assert [c.name for c in calls(first)] == ["fs_list"] and first[-1] == Done("tool_calls")
    call = calls(first)[0]
    second = await run(p, ModelRequest([ChatTurn("user", "go"), ChatTurn("assistant", "Looking.", tool_calls=(call,)),
                                        ChatTurn("tool", "x", tool_call_id=call.id, name="fs_list")]))
    assert not calls(second) and second[-1] == Done("stop")
    logged = [json.loads(line) for line in log.read_text().splitlines()]
    assert logged[0]["tools"] == ["fs_list"] and logged[1]["turns"][2] == {"role": "tool", "content": "x", "name": "fs_list"}
