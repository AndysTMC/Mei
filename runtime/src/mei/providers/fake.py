"""Scripted provider for tests, evals, and offline development.

Options (from `ProviderConfig.options`):
  reply        fixed reply text; default "Echo: <last user message>"
  chunk_chars  characters per streamed chunk (default 8)
  delay_ms     pause before each chunk (default 20)
  thinking     optional reasoning text streamed before the reply
  fail         if set, raise a ProviderError with this message after the first chunk
  fail_retryable  mark that mid-stream error as retryable (it must still not be retried)
  cut_off      if true, end the stream after the first chunk without finishing (a dropped reply)
  busy_times   the first N calls raise a retryable error before any output (like HTTP 503)
  call_log     path of a JSON-lines file; every call appends the request it got (for crash and
               disclosure tests)
  script       a list of turns, each {"text", "thinking", "tool_calls": [{"name", "arguments"}]};
               the turn used is the number of assistant turns since the last user message, so
               each tool round trip moves one step. Past the end, the reply above is used.
  scripts      {substring: script}: the script for a last user message containing the substring
               (checked before `script`; lets a test steer a task onto another script)
  cloud        report itself as a cloud provider (disclosure tests)
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator

from .base import (ChatTurn, Done, IncompleteResponse, ModelEvent, ModelRequest, ProviderError, TextDelta,
                   ThinkingDelta, ToolCall, ToolCalled, Usage)


class FakeProvider:
    label = "Fake"

    def __init__(self, options: dict) -> None:
        self.model = options.get("model", "fake-1")
        self._options = options
        self._calls = 0

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        opts = self._options
        last_user = next((t.content for t in reversed(request.messages) if t.role == "user"), "")
        if opts.get("call_log"):
            with open(opts["call_log"], "a") as f:
                f.write(json.dumps({"t": time.time(), "messages": len(request.messages), "last_user": last_user,
                                    "turns": [_logged(t) for t in request.messages],
                                    "tools": [t.name for t in request.tools]}) + "\n")
        self._calls += 1
        if self._calls <= int(opts.get("busy_times", 0)):
            raise ProviderError("Fake: HTTP 503: overloaded", retryable=True, status=503)
        turn = _scripted_turn(opts, request, last_user)
        reply = turn.get("text", "") if turn is not None else (opts.get("reply") or f"Echo: {last_user}")
        thought = turn.get("thinking", "") if turn is not None else opts.get("thinking", "")
        size = max(1, int(opts.get("chunk_chars", 8)))
        delay = max(0, int(opts.get("delay_ms", 20))) / 1000
        for i in range(0, len(thought), size):
            await asyncio.sleep(delay)
            yield ThinkingDelta(thought[i:i + size])
        for n, i in enumerate(range(0, len(reply), size)):
            await asyncio.sleep(delay)
            yield TextDelta(reply[i:i + size])
            if n == 0 and opts.get("fail"):
                raise ProviderError(str(opts["fail"]), retryable=bool(opts.get("fail_retryable")))
            if n == 0 and opts.get("cut_off"):
                raise IncompleteResponse.of(self.label)
        calls = [_call(c, f"fake_{self._calls}_{n}") for n, c in enumerate((turn or {}).get("tool_calls", []), start=1)]
        for call in calls:
            await asyncio.sleep(delay)
            yield ToolCalled(call)
        yield Usage(input_tokens=sum(len(t.content) for t in request.messages), output_tokens=len(reply))
        yield Done("tool_calls" if calls else "stop")


def _scripted_turn(opts: dict, request: ModelRequest, last_user: str) -> dict | None:
    script = next((s for key, s in (opts.get("scripts") or {}).items() if key in last_user), opts.get("script"))
    if not script:
        return None
    since_user = 0
    for turn in reversed(request.messages):
        if turn.role == "user":
            break
        since_user += turn.role == "assistant"
    return script[since_user] if since_user < len(script) else None


def _call(spec: dict, default_id: str) -> ToolCall:
    arguments = spec.get("arguments", {})
    return ToolCall(spec.get("id") or default_id, spec["name"],
                    arguments if isinstance(arguments, str) else json.dumps(arguments))


def _logged(turn: ChatTurn) -> dict:
    entry: dict = {"role": turn.role, "content": turn.content}
    if turn.tool_calls:
        entry["tool_calls"] = [{"name": c.name, "arguments": c.arguments} for c in turn.tool_calls]
    if turn.role == "tool":
        entry["name"] = turn.name
    return entry
