"""Scripted provider for tests and offline development.

Options (from `ProviderConfig.options`):
  reply        fixed reply text; default "Echo: <last user message>"
  chunk_chars  characters per streamed chunk (default 8)
  delay_ms     pause before each chunk (default 20)
  thinking     optional reasoning text streamed before the reply
  fail         if set, raise a ProviderError with this message after the first chunk
  fail_retryable  mark that mid-stream error as retryable (it must still not be retried)
  cut_off      if true, end the stream after the first chunk without finishing (a dropped reply)
  busy_times   the first N calls raise a retryable error before any output (like HTTP 503)
  call_log     path of a JSON-lines file; every call appends one record (for crash tests)
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator

from .base import Done, IncompleteResponse, ModelEvent, ModelRequest, ProviderError, TextDelta, ThinkingDelta, Usage


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
                f.write(json.dumps({"t": time.time(), "messages": len(request.messages), "last_user": last_user}) + "\n")
        self._calls += 1
        if self._calls <= int(opts.get("busy_times", 0)):
            raise ProviderError("Fake: HTTP 503: overloaded", retryable=True, status=503)
        reply = opts.get("reply") or f"Echo: {last_user}"
        size = max(1, int(opts.get("chunk_chars", 8)))
        delay = max(0, int(opts.get("delay_ms", 20))) / 1000
        for i in range(0, len(opts.get("thinking", "")), size):
            await asyncio.sleep(delay)
            yield ThinkingDelta(opts["thinking"][i:i + size])
        for n, i in enumerate(range(0, len(reply), size)):
            await asyncio.sleep(delay)
            yield TextDelta(reply[i:i + size])
            if n == 0 and opts.get("fail"):
                raise ProviderError(str(opts["fail"]), retryable=bool(opts.get("fail_retryable")))
            if n == 0 and opts.get("cut_off"):
                raise IncompleteResponse.of(self.label)
        yield Usage(input_tokens=sum(len(t.content) for t in request.messages), output_tokens=len(reply))
        yield Done("stop")
