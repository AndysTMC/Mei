"""One model call, streamed (§8.2, §12.4): coalesced deltas, draft checkpoints, transient retries.

Deltas are published every 33 ms at most; a draft is saved every 2 s or 2 KB so an interrupted
reply can still be shown. A transient refusal that comes before any output is retried with
jittered backoff: nothing was produced, so asking again can't duplicate anything.
"""

import asyncio
import logging
import random
import time
from collections.abc import Callable
from contextlib import aclosing
from dataclasses import dataclass, field, replace
from typing import Protocol

from mei.protocol import Envelope
from mei.providers.base import (Done, ModelRequest, Provider, ProviderError, Replay, ReplayData, TextDelta,
                                ThinkingDelta, ToolCall, ToolCalled, Usage)
from mei.store import repo
from mei.store.db import Store, iso_now, new_id

log = logging.getLogger("mei.engine")

DELTA_COALESCE_S = 0.033
DRAFT_EVERY_S = 2.0
DRAFT_EVERY_CHARS = 2048
CALL_TIMEOUT_S = 600.0
MAX_ATTEMPTS = 3
RETRY_BASE_S = 1.0
MAX_RETRY_WAIT_S = 60.0  # a provider asking for longer than this is better reported than waited on


class Publisher(Protocol):
    def publish(self, events: list[Envelope]) -> None: ...
    def publish_ephemeral(self, event: Envelope) -> None: ...


@dataclass
class Stream:
    """An assistant message being streamed. `text`/`thinking` hold what was already published."""

    conversation_id: str
    task_id: str
    turn_id: str
    message_id: str
    text: str = ""
    thinking: str = ""
    chunk: int = 0
    pending_text: str = ""
    pending_thinking: str = ""
    flush_handle: asyncio.TimerHandle | None = None
    draft_at: float = field(default_factory=time.monotonic)
    draft_len: int = 0

    def view(self) -> dict:
        return {"conversation_id": self.conversation_id, "task_id": self.task_id,
                "message_id": self.message_id, "text": self.text, "thinking": self.thinking,
                "chunk": self.chunk}


@dataclass
class Reply:
    text: str
    thinking: str
    calls: list[ToolCall]
    replay: Replay | None
    usage: Usage | None
    duration_ms: int
    tools_dropped: bool = False  # the model refused tools, so the call was repeated without them


class Streamer:
    def __init__(self, store: Store, publisher: Callable[[], Publisher]) -> None:
        self._store = store
        self._publisher = publisher
        self.streams: dict[str, Stream] = {}

    async def call(self, provider: Provider, request: ModelRequest, stream: Stream) -> Reply:
        """Stream one reply into `stream`. Raises ProviderError, TimeoutError, or CancelledError;
        whatever arrived before is flushed to `stream` either way."""
        self.streams[stream.message_id] = stream
        started = time.monotonic()
        calls: list[ToolCall] = []
        replay: Replay | None = None
        usage: Usage | None = None
        dropped = False
        try:
            async with asyncio.timeout(CALL_TIMEOUT_S):
                attempt = 0
                while True:
                    attempt += 1
                    try:
                        async with aclosing(provider.stream(request)) as events:
                            async for event in events:
                                if isinstance(event, TextDelta):
                                    stream.pending_text += event.text
                                    self._queue_flush(stream)
                                elif isinstance(event, ThinkingDelta):
                                    stream.pending_thinking += event.text
                                    self._queue_flush(stream)
                                elif isinstance(event, ToolCalled):
                                    calls.append(event.call)
                                elif isinstance(event, ReplayData):
                                    replay = event.replay
                                elif isinstance(event, Usage):
                                    usage = event
                                elif isinstance(event, Done):
                                    break
                        break
                    except ProviderError as e:
                        produced = stream.chunk > 0 or stream.pending_text or stream.pending_thinking or calls
                        if not produced and request.tools and _refuses_tools(e):
                            log.warning("%s; asking again without tools", e, extra={"task_id": stream.task_id})
                            request, dropped = replace(request, tools=()), True
                            continue
                        asked = e.details.get("retry_after")
                        if not e.retryable or produced or attempt >= MAX_ATTEMPTS or (asked or 0) > MAX_RETRY_WAIT_S:
                            raise
                        # Back off, and at least as long as the provider asked (§8.2: honor Retry-After).
                        delay = max(RETRY_BASE_S * (3 ** (attempt - 1)) * random.uniform(0.8, 1.2), asked or 0.0)
                        log.warning("%s; retrying in %.1f s (attempt %d of %d)", e, delay, attempt + 1, MAX_ATTEMPTS,
                                    extra={"task_id": stream.task_id})
                        await asyncio.sleep(delay)
        finally:
            self.flush(stream)
            self.streams.pop(stream.message_id, None)
        return Reply(stream.text, stream.thinking, calls, replay, usage, int((time.monotonic() - started) * 1000),
                     tools_dropped=dropped)

    def _queue_flush(self, stream: Stream) -> None:
        if stream.flush_handle is None:
            stream.flush_handle = asyncio.get_running_loop().call_later(DELTA_COALESCE_S, self.flush, stream)

    def flush(self, stream: Stream) -> None:
        if stream.flush_handle is not None:
            stream.flush_handle.cancel()
            stream.flush_handle = None
        if not stream.pending_text and not stream.pending_thinking:
            return
        text, thinking = stream.pending_text, stream.pending_thinking
        stream.pending_text = stream.pending_thinking = ""
        stream.text += text
        stream.thinking += thinking
        stream.chunk += 1
        self._publisher().publish_ephemeral(Envelope(
            type="message.delta", event_id=new_id(), epoch=self._store.epoch, at=iso_now(), required=False,
            conversation_id=stream.conversation_id, task_id=stream.task_id,
            payload={"message_id": stream.message_id, "chunk": stream.chunk, "text": text, "thinking": thinking}))
        size = len(stream.text) + len(stream.thinking)
        if size - stream.draft_len >= DRAFT_EVERY_CHARS or time.monotonic() - stream.draft_at >= DRAFT_EVERY_S:
            repo.save_draft(self._store, stream.turn_id, stream.text, stream.thinking, stream.chunk)
            stream.draft_at = time.monotonic()
            stream.draft_len = size


def _refuses_tools(e: ProviderError) -> bool:
    """A model that can't use tools says so with a 400-class error that mentions them."""
    return e.status in (400, 404, 422) and "tool" in e.message.lower()
