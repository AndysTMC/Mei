"""Anthropic Messages API adapter (streaming).

Tool results for one assistant turn go back in a single user message. Thinking blocks (with their
signatures) are returned as replay data: the API requires them before the `tool_use` blocks of the
turn being continued.
"""

import re
from collections.abc import AsyncIterator

import httpx

from .base import (ChatTurn, Done, IncompleteResponse, ModelEvent, ModelRequest, ProviderError, Replay,
                   ReplayData, TextDelta, ThinkingDelta, ToolCall, ToolCalled, Usage, arguments_object,
                   replay_for, tool_groups)
from .http_stream import error_message, first_int, loads, stream_post

MAX_TOKENS = 16384
WIRE = "anthropic"
_ADAPTIVE_THINKING = re.compile(r"(?:opus-4-[678]|sonnet-4-6|fable-5|sonnet-5|mythos-5)")


class AnthropicProvider:
    def __init__(self, client: httpx.AsyncClient, *, label: str, url: str, model: str,
                 headers: dict[str, str] | None = None) -> None:
        if not model:
            raise ProviderError(f"{label}: no model selected")
        self.label = label
        self.model = model
        self._client = client
        self._url = url
        self._headers = {**(headers or {}), "anthropic-version": "2023-06-01"}

    def body(self, request: ModelRequest) -> dict:
        system = "\n\n".join(t.content for t in request.messages if t.role == "system")
        body = {"model": self.model, "max_tokens": MAX_TOKENS, "stream": True,
                "messages": _messages([t for t in request.messages if t.role != "system"])}
        if system:
            body["system"] = system
        if request.tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters}
                             for t in request.tools]
        if _ADAPTIVE_THINKING.search(self.model.lower()):
            body["thinking"] = {"type": "adaptive", "display": "summarized"}
        return body

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        input_tokens = None
        finished = False
        blocks: dict[int, dict] = {}  # by content block index, in arrival order
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
            elif kind == "content_block_start":
                block = event.get("content_block")
                if isinstance(block, dict) and isinstance(event.get("index"), int):
                    blocks[event["index"]] = {**block, "partial_json": ""}
            elif kind == "content_block_delta":
                delta = event.get("delta") or {}
                block = blocks.get(event.get("index"))
                if delta.get("type") == "text_delta" and delta.get("text"):
                    yield TextDelta(delta["text"])
                elif delta.get("type") == "thinking_delta" and delta.get("thinking"):
                    if block is not None:
                        block["thinking"] = block.get("thinking", "") + delta["thinking"]
                    yield ThinkingDelta(delta["thinking"])
                elif block is not None and delta.get("type") == "signature_delta":
                    block["signature"] = block.get("signature", "") + (delta.get("signature") or "")
                elif block is not None and delta.get("type") == "input_json_delta":
                    block["partial_json"] += delta.get("partial_json") or ""
            elif kind == "message_delta":
                usage = event.get("usage") or {}
                yield Usage(input_tokens, first_int(usage, "output_tokens"))
            elif kind == "message_stop":
                finished = True
                break
        if not finished:
            raise IncompleteResponse.of(self.label)
        calls = [ToolCall(b.get("id") or f"toolu_{i}", b.get("name") or "", b["partial_json"] or "{}")
                 for i, b in blocks.items() if b.get("type") == "tool_use" and b.get("name")]
        for call in calls:
            yield ToolCalled(call)
        reasoning = [_reasoning_block(b) for b in blocks.values() if b.get("type") in ("thinking", "redacted_thinking")]
        if calls and reasoning:
            yield ReplayData(Replay(WIRE, {"blocks": reasoning}))
        yield Done("tool_calls" if calls else "stop")


def _reasoning_block(block: dict) -> dict:
    if block["type"] == "redacted_thinking":
        return {"type": "redacted_thinking", "data": block.get("data", "")}
    return {"type": "thinking", "thinking": block.get("thinking", ""), "signature": block.get("signature", "")}


def _messages(turns: list[ChatTurn]) -> list[dict]:
    out: list[dict] = []
    for item in tool_groups(turns):
        if isinstance(item, list):
            out.append({"role": "user", "content": [_tool_result(t) for t in item]})
        elif item.role == "assistant":
            out.append({"role": "assistant", "content": _assistant_content(item)})
        elif out and out[-1]["role"] == "user":
            # A message after tool results (the user steering mid-task) joins them: roles alternate.
            previous = out[-1]["content"]
            blocks = previous if isinstance(previous, list) else [{"type": "text", "text": previous}]
            out[-1]["content"] = [*blocks, {"type": "text", "text": item.content}]
        else:
            out.append({"role": "user", "content": item.content})
    return out


def _assistant_content(turn: ChatTurn) -> str | list[dict]:
    replay = replay_for(turn, WIRE) or {}
    if not turn.tool_calls and not replay:
        return turn.content
    blocks = list(replay.get("blocks", []))
    if turn.content:
        blocks.append({"type": "text", "text": turn.content})
    blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": arguments_object(c.arguments)}
               for c in turn.tool_calls]
    return blocks


def _tool_result(turn: ChatTurn) -> dict:
    block = {"type": "tool_result", "tool_use_id": turn.tool_call_id, "content": turn.content}
    if turn.is_error:
        block["is_error"] = True
    return block


def _overloaded(event: dict) -> bool:
    err = event.get("error")
    return isinstance(err, dict) and err.get("type") in ("overloaded_error", "rate_limit_error", "api_error")
