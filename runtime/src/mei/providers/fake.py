"""Scripted provider for tests and offline development.

Options (from `ProviderConfig.options`):
  reply        fixed reply text; default "Echo: <last user message>"
  chunk_chars  characters per streamed chunk (default 8)
  delay_ms     pause before each chunk (default 20)
  thinking     optional reasoning text streamed before the reply
  fail         if set, raise a ProviderError with this message after the first chunk
  call_log     path of a JSON-lines file; every call appends one record (for crash tests)
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator

from .base import Done, ModelEvent, ModelRequest, ProviderError, TextDelta, ThinkingDelta, Usage


class FakeProvider:
    label = "Fake"

    def __init__(self, options: dict) -> None:
        self.model = options.get("model", "fake-1")
        self._options = options

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        opts = self._options
        last_user = next((t.content for t in reversed(request.messages) if t.role == "user"), "")
        if opts.get("call_log"):
            with open(opts["call_log"], "a") as f:
                f.write(json.dumps({"t": time.time(), "messages": len(request.messages), "last_user": last_user}) + "\n")
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
                raise ProviderError(str(opts["fail"]))
        yield Usage(input_tokens=sum(len(t.content) for t in request.messages), output_tokens=len(reply))
        yield Done("stop")
