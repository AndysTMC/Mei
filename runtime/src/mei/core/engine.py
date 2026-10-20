"""Task engine for Stage 1: durable chat turns (architecture §7–§8, §15).

Commands are synchronous: they validate, change the store in one transaction, publish the
committed events, and only then schedule work. Model calls run as asyncio tasks. Waiting is a
stored state, so a restart can always pick up from the database.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

import msgspec

from mei.protocol import (MAX_INPUT_CHARS, ConversationCommandArgs, Envelope, ProtocolError,
                          ProviderConfig, SubmitInputArgs, TaskCommandArgs, UpdateConfigArgs)
from mei.providers.base import Done, ModelRequest, Provider, ProviderError, TextDelta, ThinkingDelta, Usage
from mei.providers.factory import label_of
from mei.providers.openai_chat import to_turns
from mei.store import repo
from mei.store.db import Store, Tx, iso_now, new_id

from .states import TERMINAL, TaskState

log = logging.getLogger("mei.engine")

DELTA_COALESCE_S = 0.033
DRAFT_EVERY_S = 2.0
DRAFT_EVERY_CHARS = 2048
TURN_TIMEOUT_S = 600.0
MAX_ATTEMPTS = 3
RETRY_BASE_S = 1.0
S = TaskState


class Publisher(Protocol):
    def publish(self, events: list[Envelope]) -> None: ...
    def publish_ephemeral(self, event: Envelope) -> None: ...


ProviderFactory = Callable[[ProviderConfig], Awaitable[Provider]]


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


class Engine:
    def __init__(self, store: Store, publisher: Publisher | None, provider_factory: ProviderFactory,
                 *, max_concurrent: int = 2) -> None:
        self.store = store
        self.publisher = publisher
        self._make_provider = provider_factory
        self._slots = asyncio.Semaphore(max_concurrent)
        self._runners: dict[str, asyncio.Task] = {}
        self._shutting_down = False
        self.streams: dict[str, Stream] = {}

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def recover(self) -> None:
        """Startup reconciliation (§15). Call once, before accepting commands."""
        to_start: list[str] = []
        with self.store.tx() as tx:
            tx.execute("UPDATE turns SET state = 'lost' WHERE state = 'running' AND epoch != ?", (self.store.epoch,))
            placeholders = ",".join("?" for _ in TERMINAL)
            for row in tx.execute(f"SELECT * FROM tasks WHERE state NOT IN ({placeholders})", tuple(TERMINAL)).fetchall():
                state = S(row["state"])
                if state == S.ACCEPTED:
                    to_start.append(row["id"])
                elif state == S.CANCEL_REQUESTED:
                    task = repo.set_task_state(tx, row["id"], S.CANCELLED)
                    repo.finished_event(tx, task, draft=_draft(tx, row["id"]))
                elif state != S.INTERRUPTED:
                    # The model call or action was in flight when the runtime died. Don't re-send it
                    # automatically: the upstream call may already have been billed (§15).
                    task = repo.set_task_state(tx, row["id"], S.INTERRUPTED,
                                               error="Mei stopped while this reply was being written")
                    repo.finished_event(tx, task, draft=_draft(tx, row["id"]))
        self.publisher.publish(tx.events)
        for task_id in to_start:
            self._schedule(task_id)
        if tx.events or to_start:
            log.info("recovered %d task changes, restarted %d queued tasks", len(tx.events), len(to_start))

    async def shutdown(self) -> None:
        self._shutting_down = True
        runners = list(self._runners.values())
        for runner in runners:
            runner.cancel()
        await asyncio.gather(*runners, return_exceptions=True)

    # ── Commands ────────────────────────────────────────────────────────────

    def submit_input(self, args: SubmitInputArgs) -> dict:
        text = args.text.strip()
        if not text:
            raise ProtocolError("InvalidArgument", "message is empty")
        if len(text) > MAX_INPUT_CHARS:
            raise ProtocolError("InvalidArgument", f"message is longer than {MAX_INPUT_CHARS} characters")
        _revision, config = repo.get_config(self.store)
        if not config.provider.id:
            raise ProtocolError("Unsupported", "no model provider is configured")

        def apply(tx: Tx) -> tuple[dict, list[str]]:
            if args.conversation_id is None:
                conversation_id = repo.create_conversation(tx, text)["id"]
            else:
                if repo.get_conversation(tx, args.conversation_id) is None:
                    raise ProtocolError("NotFound", "no such conversation")
                conversation_id = args.conversation_id
                if repo.blocking_task(tx, conversation_id) is not None:
                    raise ProtocolError("Busy", "Mei is still answering in this conversation")
                for old in repo.interrupted_tasks(tx, conversation_id):  # superseded by the new message
                    repo.finished_event(tx, repo.set_task_state(tx, old["id"], S.CANCELLED,
                                                                error="replaced by a new message"))
            message = repo.add_message(tx, conversation_id, "user", text)
            task = repo.create_task(tx, conversation_id, message["id"], msgspec.to_builtins(config.provider))
            result = {"conversation_id": conversation_id, "task_id": task["id"], "message_id": message["id"]}
            return result, [task["id"]]

        return self._command("SubmitInput", args, apply)

    def cancel(self, args: TaskCommandArgs) -> dict:
        def apply(tx: Tx) -> tuple[dict, list[str]]:
            row = repo.get_task(tx, args.task_id)
            if row is None:
                raise ProtocolError("NotFound", "no such task")
            state = S(row["state"])
            if state in TERMINAL or state == S.CANCEL_REQUESTED:
                return {"task_id": args.task_id, "state": state}, []
            if state in (S.ACCEPTED, S.INTERRUPTED):
                # Not running (at most waiting for a slot): stop it outright. A waiting runner finds
                # the terminal state when it gets its slot and returns.
                task = repo.set_task_state(tx, args.task_id, S.CANCELLED)
                repo.finished_event(tx, task, draft=_draft(tx, args.task_id) if state == S.INTERRUPTED else None)
                return {"task_id": args.task_id, "state": S.CANCELLED}, []
            # Persist the request before signalling the runner (invariant 7).
            repo.set_task_state(tx, args.task_id, S.CANCEL_REQUESTED)
            return {"task_id": args.task_id, "state": S.CANCEL_REQUESTED}, []

        result = self._command("Cancel", args, apply)
        runner = self._runners.get(args.task_id)
        if runner is not None and result["state"] == S.CANCEL_REQUESTED:
            runner.cancel()
        return result

    def resume(self, args: TaskCommandArgs) -> dict:
        def apply(tx: Tx) -> tuple[dict, list[str]]:
            row = repo.get_task(tx, args.task_id)
            if row is None:
                raise ProtocolError("NotFound", "no such task")
            if S(row["state"]) != S.INTERRUPTED:
                raise ProtocolError("Conflict", f"only interrupted tasks can be resumed (this one is {row['state']})")
            if repo.blocking_task(tx, row["conversation_id"]) is not None:
                raise ProtocolError("Busy", "Mei is still answering in this conversation")
            return {"task_id": args.task_id, "state": S.INTERRUPTED}, [args.task_id]

        return self._command("Resume", args, apply)

    def delete_conversation(self, args: ConversationCommandArgs) -> dict:
        def apply(tx: Tx) -> tuple[dict, list[str]]:
            if repo.blocking_task(tx, args.conversation_id) is not None:
                raise ProtocolError("Busy", "stop the reply before deleting this conversation")
            repo.delete_conversation(tx, args.conversation_id)
            return {"conversation_id": args.conversation_id, "deleted": True}, []

        return self._command("DeleteConversation", args, apply)

    def update_config(self, args: UpdateConfigArgs) -> dict:
        revision, current = repo.get_config(self.store)
        if args.revision == revision and current == args.config:
            # Nothing changes, so nothing is written or announced. Clients that re-push on
            # config.changed would otherwise feed each other forever.
            return {"revision": revision, "changed": False}
        with self.store.tx() as tx:
            revision = repo.put_config(tx, args.revision, args.config)
        self.publisher.publish(tx.events)
        return {"revision": revision, "changed": True}

    def get_config(self) -> dict:
        revision, config = repo.get_config(self.store)
        return {"revision": revision, "config": msgspec.to_builtins(config)}

    def _command(self, method: str, args, apply: Callable[[Tx], tuple[dict, list[str]]]) -> dict:
        digest = repo.request_hash(method, args)
        with self.store.tx() as tx:
            prior = repo.find_command(tx, args.command_id, method, digest)
            if prior is not None:
                return {**prior, "duplicate": True}
            result, to_start = apply(tx)
            repo.record_command(tx, args.command_id, method, digest, result)
        self.publisher.publish(tx.events)
        for task_id in to_start:
            self._schedule(task_id)
        return {**result, "duplicate": False}

    # ── Running a turn ──────────────────────────────────────────────────────

    def _schedule(self, task_id: str) -> None:
        if task_id in self._runners or self._shutting_down:
            return
        runner = asyncio.get_running_loop().create_task(self._run(task_id), name=f"task-{task_id}")
        self._runners[task_id] = runner
        runner.add_done_callback(lambda _t: self._runners.pop(task_id, None))

    async def _run(self, task_id: str) -> None:
        async with self._slots:
            row = repo.get_task(self.store, task_id)
            if row is None or S(row["state"]) not in (S.ACCEPTED, S.INTERRUPTED):
                return
            provider_cfg = msgspec.convert(_loads(row["provider"]), ProviderConfig)
            label = {"id": provider_cfg.id, "label": label_of(provider_cfg), "model": provider_cfg.model}
            with self.store.tx() as tx:
                repo.set_task_state(tx, task_id, S.RUNNING)
                turn = repo.begin_turn(tx, task_id, self.store.epoch, label)
            self.publisher.publish(tx.events)
            stream = Stream(row["conversation_id"], task_id, turn["id"], turn["message_id"])
            self.streams[stream.message_id] = stream
            started = time.monotonic()
            usage: Usage | None = None
            try:
                provider = await self._make_provider(provider_cfg)
                messages = repo.history(self.store, row["conversation_id"],
                                        up_to_ordinal=repo.message_ordinal(self.store, row["input_message_id"]))
                request = ModelRequest(to_turns(messages))
                async with asyncio.timeout(TURN_TIMEOUT_S):
                    for attempt in range(1, MAX_ATTEMPTS + 1):
                        try:
                            async for event in provider.stream(request):
                                if isinstance(event, TextDelta):
                                    stream.pending_text += event.text
                                    self._queue_flush(stream)
                                elif isinstance(event, ThinkingDelta):
                                    stream.pending_thinking += event.text
                                    self._queue_flush(stream)
                                elif isinstance(event, Usage):
                                    usage = event
                                elif isinstance(event, Done):
                                    break
                            break
                        except ProviderError as e:
                            # Retry only transient refusals that arrived before any output: the
                            # provider didn't produce anything, so asking again can't duplicate it.
                            started_output = stream.chunk > 0 or stream.pending_text or stream.pending_thinking
                            if not e.retryable or started_output or attempt == MAX_ATTEMPTS:
                                raise
                            delay = RETRY_BASE_S * (3 ** (attempt - 1)) * random.uniform(0.8, 1.2)
                            log.warning("%s; retrying in %.1f s (attempt %d of %d)", e, delay, attempt + 1,
                                        MAX_ATTEMPTS, extra={"task_id": task_id})
                            await asyncio.sleep(delay)
                self._flush(stream)
                metadata = {**label, "duration_ms": int((time.monotonic() - started) * 1000)}
                if usage is not None:
                    metadata["tokens"] = {"input": usage.input_tokens, "output": usage.output_tokens}
                self._finish(task_id, stream, S.COMPLETED, message_metadata=metadata)
            except asyncio.CancelledError:
                self._flush(stream)
                if self._shutting_down:
                    self._finish(task_id, stream, S.INTERRUPTED, error="Mei was restarting", turn_state="lost")
                else:
                    self._finish(task_id, stream, S.CANCELLED)
            except ProviderError as e:
                self._flush(stream)
                self._finish(task_id, stream, S.FAILED, error=str(e))
            except TimeoutError:
                self._flush(stream)
                self._finish(task_id, stream, S.FAILED, error=f"no complete reply within {int(TURN_TIMEOUT_S)} s")
            except Exception:
                log.exception("turn failed", extra={"task_id": task_id})
                self._flush(stream)
                self._finish(task_id, stream, S.FAILED, error="internal error (see the Mei runtime log)")
            finally:
                self.streams.pop(stream.message_id, None)

    def _finish(self, task_id: str, stream: Stream, to: TaskState, *, error: str | None = None,
                message_metadata: dict | None = None, turn_state: str = "done") -> None:
        with self.store.tx() as tx:
            current = S(repo.get_task(tx, task_id)["state"])
            if current in TERMINAL:
                return
            if current == S.CANCEL_REQUESTED and to != S.FAILED:
                to = S.CANCELLED  # the user's stop wins, even over a reply that just completed
            elif to == S.CANCELLED:
                to = S.INTERRUPTED  # cancelled without a user request: treat as an interruption
            draft = {"text": stream.text, "thinking": stream.thinking}
            if to == S.COMPLETED:
                repo.add_message(tx, stream.conversation_id, "assistant", stream.text, task_id=task_id,
                                 thinking=stream.thinking or None, metadata=message_metadata,
                                 message_id=stream.message_id)
            else:
                tx.execute("UPDATE turns SET draft_text = ?, draft_thinking = ?, draft_chunk = ? WHERE id = ?",
                           (stream.text, stream.thinking, stream.chunk, stream.turn_id))
            repo.finish_turn(tx, stream.turn_id, turn_state)
            task = repo.set_task_state(tx, task_id, to, error=error)
            repo.finished_event(tx, task, draft=None if to == S.COMPLETED else draft)
        self.publisher.publish(tx.events)

    def _queue_flush(self, stream: Stream) -> None:
        if stream.flush_handle is None:
            stream.flush_handle = asyncio.get_running_loop().call_later(DELTA_COALESCE_S, self._flush, stream)

    def _flush(self, stream: Stream) -> None:
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
        self.publisher.publish_ephemeral(Envelope(
            type="message.delta", event_id=new_id(), epoch=self.store.epoch, at=iso_now(), required=False,
            conversation_id=stream.conversation_id, task_id=stream.task_id,
            payload={"message_id": stream.message_id, "chunk": stream.chunk, "text": text, "thinking": thinking}))
        size = len(stream.text) + len(stream.thinking)
        if size - stream.draft_len >= DRAFT_EVERY_CHARS or time.monotonic() - stream.draft_at >= DRAFT_EVERY_S:
            repo.save_draft(self.store, stream.turn_id, stream.text, stream.thinking, stream.chunk)
            stream.draft_at = time.monotonic()
            stream.draft_len = size


def _draft(tx: Tx, task_id: str) -> dict | None:
    turn = repo.latest_turn(tx, task_id)
    return None if turn is None else {"text": turn["draft_text"], "thinking": turn["draft_thinking"]}


def _loads(text: str) -> dict:
    return msgspec.json.decode(text)

