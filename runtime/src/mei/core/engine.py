"""Task engine: commands, scheduling, and recovery (architecture §7–§8, §15).

Commands are synchronous: they validate, change the store in one transaction, publish the committed
events, and only then schedule work. Each runnable task gets one asyncio runner, which drives the
agent loop (core/loop.py) until the task waits or ends. Waiting is a stored state, so a restart can
always pick up from the database.
"""

import asyncio
import json
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urlsplit

import msgspec

from mei.capabilities.base import Env, backups_dir
from mei.capabilities.computer import HANDOFF_DONE
from mei.capabilities.registry import Registry
from mei.core.states import TERMINAL, Disposition, Execution, TaskState
from mei.protocol import (MAX_INPUT_CHARS, AnswerInputArgs, Attachment, Config, ConversationCommandArgs, ForgetMemoryArgs,
                          MemoriesArgs, ProtocolError, UpdateMemoryArgs,
                          ProviderConfig, ResolveApprovalArgs, RevokeGrantArgs, SubmitInputArgs, TaskCommandArgs,
                          UpdateConfigArgs, active_provider)
from mei.policy.engine import Subject, rules_for
from mei.providers.base import Provider
from mei.store import agent, repo
from mei.store import memory as mem
from mei.store.db import Store, Tx, new_id, now_ms

from . import finish, ledger, recovery, remember
from .memories import StoreMemory
from .loop import MORE_CALLS, MORE_TIME_MS, Deps, TaskLoop
from .streaming import Publisher, Streamer

log = logging.getLogger("mei.engine")
S, E = TaskState, Execution
ProviderFactory = Callable[[ProviderConfig], Awaitable[Provider]]


class Engine:
    def __init__(self, store: Store, publisher: Publisher | None, provider_factory: ProviderFactory, *,
                 registry: Registry | None = None, env: Env | None = None, max_concurrent: int = 2,
                 boundary: Callable[[str], None] = lambda _name: None) -> None:
        self.store = store
        self.publisher = publisher
        self._slots = asyncio.Semaphore(max_concurrent)
        self._runners: dict[str, asyncio.Task] = {}
        self._shutting_down = False
        self.env = env or Env(home=Path.home(), data_dir=store.path.parent)
        if self.env.memory is None:
            self.env.memory = StoreMemory(store, self._publish)
        self.streamer = Streamer(store, lambda: self.publisher)
        self.loop = TaskLoop(Deps(store=store, publish=self._publish, streamer=self.streamer,
                                  make_provider=provider_factory, registry=registry or Registry([]), env=self.env,
                                  boundary=boundary))

    @property
    def streams(self) -> dict:
        return self.streamer.streams

    def _publish(self, events) -> None:
        self.publisher.publish(events)

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def recover(self) -> None:
        """Startup reconciliation (§15). Call once, before accepting commands."""
        if mem.reindex(self.store):
            log.warning("the search indexes disagreed with their tables and were rebuilt")
        with self.store.tx() as tx:
            to_start = recovery.reconcile(tx, self.store.epoch)
        self._publish(tx.events)
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
        provider = active_provider(config)
        if not provider.id:
            raise ProtocolError("Unsupported", "no model provider is configured")

        attached = _attached(args.attachment)
        metadata = {**(attached or {}), **({"source": "voice"} if args.source == "voice" else {})} or None

        def apply(tx: Tx) -> tuple[dict, list[str]]:
            if args.conversation_id is None:
                conversation_id = repo.create_conversation(tx, text)["id"]
            else:
                if repo.get_conversation(tx, args.conversation_id) is None:
                    raise ProtocolError("NotFound", "no such conversation")
                conversation_id = args.conversation_id
                active = repo.blocking_task(tx, conversation_id)
                if active is not None:
                    return self._steer(tx, active, text, attached, metadata)
                for old in repo.interrupted_tasks(tx, conversation_id):  # superseded by the new message
                    ledger.cancel_now(tx, old["id"], error="replaced by a new message")
            message = repo.add_message(tx, conversation_id, "user", text, metadata=metadata)
            task = repo.create_task(tx, conversation_id, message["id"], msgspec.to_builtins(provider))
            if attached:
                _taint(tx, task["id"], attached)
            result = {"conversation_id": conversation_id, "task_id": task["id"], "message_id": message["id"],
                      "steer": False}
            return result, [task["id"]]

        return self._command("SubmitInput", args, apply)

    def _steer(self, tx: Tx, active, text: str, attached: dict | None, metadata: dict | None) -> tuple[dict, list[str]]:
        """New input while a task runs joins that task (§8.1). Unstarted actions are skipped and a
        pending approval or question is superseded; the model then reads the new message."""
        state = S(active["state"])
        if state == S.CANCEL_REQUESTED:
            raise ProtocolError("Busy", "Mei is stopping the current task")
        message = repo.add_message(tx, active["conversation_id"], "user", text, task_id=active["id"], metadata=metadata)
        if attached:
            _taint(tx, active["id"], attached)
        result = {"conversation_id": active["conversation_id"], "task_id": active["id"], "message_id": message["id"],
                  "steer": True}
        if state not in (S.WAITING_APPROVAL, S.WAITING_INPUT):
            return result, []  # running or queued: the loop sees the message at its next step
        task = repo.task_dict(active)
        batch = agent.open_batch(tx, active["id"])
        if batch is not None:
            ledger.skip_rest(tx, task, batch["id"], "the person sent a new message instead")
        request = agent.pending_input(tx, active["id"])
        if request is not None:
            agent.close_input_request(tx, request["id"], "superseded")
        tx.execute("UPDATE tasks SET call_budget = MAX(call_budget, model_calls + ?) WHERE id = ?",
                   (MORE_CALLS, active["id"]))  # they're here and engaged: a fresh step allowance
        repo.set_task_state(tx, active["id"], S.RUNNING)
        return result, [active["id"]]

    def cancel(self, args: TaskCommandArgs) -> dict:
        def apply(tx: Tx) -> tuple[dict, list[str]]:
            row = repo.get_task(tx, args.task_id)
            if row is None:
                raise ProtocolError("NotFound", "no such task")
            state = S(row["state"])
            if state in TERMINAL or state == S.CANCEL_REQUESTED:
                return {"task_id": args.task_id, "state": state}, []
            if state in (S.ACCEPTED, S.INTERRUPTED, S.WAITING_APPROVAL, S.WAITING_INPUT, S.WAITING_RESOURCE):
                # Nothing is running (at most a runner waits for a slot; it finds the terminal state).
                draft = recovery.draft(tx, args.task_id) if state == S.INTERRUPTED else None
                ledger.cancel_now(tx, args.task_id, draft=draft)
                return {"task_id": args.task_id, "state": S.CANCELLED}, []
            # Persist the request before signalling the runner (invariant 7).
            repo.set_task_state(tx, args.task_id, S.CANCEL_REQUESTED)
            return {"task_id": args.task_id, "state": S.CANCEL_REQUESTED}, []

        result = self._command("Cancel", args, apply)
        runner = self._runners.get(args.task_id)
        if result["state"] == S.CANCEL_REQUESTED:
            if runner is not None:
                runner.cancel()
            else:
                self._settle_cancel(args.task_id)
        return result

    def _settle_cancel(self, task_id: str) -> None:
        with self.store.tx() as tx:
            if S(repo.get_task(tx, task_id)["state"]) == S.CANCEL_REQUESTED:
                ledger.cancel_now(tx, task_id)
        self._publish(tx.events)

    def resume(self, args: TaskCommandArgs) -> dict:
        def apply(tx: Tx) -> tuple[dict, list[str]]:
            row = repo.get_task(tx, args.task_id)
            if row is None:
                raise ProtocolError("NotFound", "no such task")
            if S(row["state"]) == S.WAITING_RESOURCE:  # paused while the person used the computer: go on now
                repo.set_task_state(tx, args.task_id, S.RUNNING)
                return {"task_id": args.task_id, "state": S.RUNNING}, []
            if S(row["state"]) != S.INTERRUPTED:
                raise ProtocolError("Conflict", f"only interrupted tasks can be resumed (this one is {row['state']})")
            if repo.blocking_task(tx, row["conversation_id"]) is not None:
                raise ProtocolError("Busy", "Mei is still answering in this conversation")
            return {"task_id": args.task_id, "state": S.INTERRUPTED}, [args.task_id]

        return self._command("Resume", args, apply)

    def stop_computer_use(self) -> list[str]:
        """The kill switch's second step (§10.3), after the worker is dead: cancel every unfinished task
        that used the computer."""
        marks = ",".join("?" for _ in TERMINAL)
        rows = self.store.read(f"SELECT DISTINCT t.id FROM tasks t JOIN actions a ON a.task_id = t.id "
                               f"WHERE a.tool LIKE 'desktop\\_%' ESCAPE '\\' AND t.state NOT IN ({marks})",
                               tuple(TERMINAL))
        for row in rows:
            self.cancel(TaskCommandArgs(command_id=new_id(), task_id=row["id"]))
        return [row["id"] for row in rows]

    def resolve_approval(self, args: ResolveApprovalArgs, decided_by: str) -> dict:
        """The person's answer on an approval card. Bound to the exact params it was asked for."""
        def apply(tx: Tx) -> tuple[dict, list[str]]:
            approval = agent.get_approval(tx, args.approval_id)
            if approval is None:
                raise ProtocolError("NotFound", "no such approval")
            if approval["state"] != "pending":
                raise ProtocolError("Conflict", f"this approval was already {approval['state']}")
            action = agent.get_action(tx, approval["action_id"])
            if E(action["execution"]) != E.AWAITING_APPROVAL or action["params_hash"] != approval["params_hash"]:
                raise ProtocolError("Conflict", "the action changed since it was shown")
            task = repo.task_dict(repo.get_task(tx, approval["task_id"]))
            card = json.loads(approval["card"])
            if args.decision == "deny":
                agent.resolve_approval(tx, approval["id"], "denied", decided_by=decided_by)
                ledger.finish_action(tx, task, action, E.DENIED, "The person declined this. Don't try another way "
                                     "around it; tell them what you couldn't do.", is_error=True)
            else:
                if args.scope not in card.get("scopes", ["once"]):
                    raise ProtocolError("InvalidArgument", f"this card doesn't offer “{args.scope}”")
                agent.resolve_approval(tx, approval["id"], "allowed", scope=args.scope, decided_by=decided_by)
                agent.update_action(tx, action["id"], E.AUTHORIZED)
                if args.scope in ("task", "always"):
                    subjects = tuple(msgspec.convert(r, Subject) for r in json.loads(action["resources"]))
                    agent.create_grant(tx, task_id=task["id"] if args.scope == "task" else None,
                                       capability=action["capability"],
                                       rules=[msgspec.to_builtins(r) for r in rules_for(subjects)],
                                       description=card.get("scope_text", {}).get(args.scope, card.get("title", "")),
                                       approval_id=approval["id"])
            repo.set_task_state(tx, task["id"], S.RUNNING)
            return {"approval_id": approval["id"], "state": "denied" if args.decision == "deny" else "allowed"}, \
                [task["id"]]

        return self._command("ResolveApproval", args, apply)

    def answer_input(self, args: AnswerInputArgs) -> dict:
        def apply(tx: Tx) -> tuple[dict, list[str]]:
            request = agent.get_input_request(tx, args.request_id)
            if request is None:
                raise ProtocolError("NotFound", "no such question")
            if request["state"] != "pending":
                raise ProtocolError("Conflict", f"this question was already {request['state']}")
            spec = json.loads(request["spec"])
            value = _valid_answer(spec, args.value)
            task = repo.task_dict(repo.get_task(tx, request["task_id"]))
            agent.close_input_request(tx, request["id"], "answered", answer=value)
            if request["kind"] == "continue" and value == "Stop":
                final = repo.set_task_state(tx, task["id"], S.BLOCKED, error="Stopped at the step limit")
                repo.finished_event(tx, final)
                return {"request_id": request["id"], "state": "answered"}, []
            if request["kind"] == "continue":
                tx.execute("UPDATE tasks SET call_budget = model_calls + ?, time_budget_ms = active_ms + ? "
                           "WHERE id = ?", (MORE_CALLS, MORE_TIME_MS, task["id"]))
            else:
                self._answer_action(tx, task, request, value)
            repo.set_task_state(tx, task["id"], S.RUNNING)
            return {"request_id": request["id"], "state": "answered"}, [task["id"]]

        return self._command("AnswerInput", args, apply)

    def _answer_action(self, tx: Tx, task: dict, request, value) -> None:
        action = agent.get_action(tx, request["action_id"])
        if request["kind"] == "question":
            agent.update_action(tx, action["id"], E.STARTED, epoch=self.store.epoch)
            ledger.finish_action(tx, task, action, E.SUCCEEDED, finish.answer_text(json.loads(request["spec"]), value),
                                 is_error=False, result={"ok": True, "summary": "Asked you a question"})
            return
        if request["kind"] == "handoff":  # the person did a step Mei may not (a password field)
            done = value == HANDOFF_DONE
            ledger.finish_action(tx, task, action, E.SUCCEEDED if done else E.FAILED,
                                 "The person filled it in themselves. Observe the window again before going on."
                                 if done else "The person didn't fill it in.", is_error=not done,
                                 result={"ok": done, "summary": "You filled in a field" if done else "Skipped a field"})
            return
        yes, no, _unsure = ledger.IN_DOUBT_CHOICES  # an action in doubt after a restart (§15)
        if value == yes:
            ledger.finish_action(tx, task, action, E.SUCCEEDED, "The person confirmed this was done.", is_error=False,
                                 disposition=Disposition.CONFIRMED, result={"ok": True, "summary": action["description"]})
        elif value == no:
            ledger.finish_action(tx, task, action, E.FAILED, "The person says this didn't happen. You can try again.",
                                 is_error=True, disposition=Disposition.NONE, error="interrupted")
        else:
            ledger.finish_action(tx, task, action, E.ABANDONED, "Nobody knows whether this happened; don't assume "
                                 "it did. Check before relying on it.", is_error=True, disposition=Disposition.UNKNOWN)

    # ── Memory (§17.7) ──────────────────────────────────────────────────────

    def memories(self, args: MemoriesArgs) -> dict:
        rows = mem.listed(self.store, status=args.status or None, text=args.query)
        pending = self.store.read_one("SELECT count(*) AS n FROM memories WHERE status = 'pending_review'")["n"]
        return {"memories": [mem.memory_view(r) for r in rows], "pending": pending}

    def update_memory(self, args: UpdateMemoryArgs, *, from_shell: bool) -> dict:
        patch = {k: v for k, v in msgspec.structs.asdict(args.patch).items() if v is not None}
        if "text" in patch and (not patch["text"].strip() or remember.judge(
                patch["text"], [patch["text"]], tainted=False, auto_save=True).status == "refused"):
            raise ProtocolError("InvalidArgument", "a memory is one fact, without keys or tokens")

        def apply(tx: Tx) -> tuple[dict, list[str]]:
            row = mem.get_memory(tx, args.memory_id)
            if row is None:
                raise ProtocolError("NotFound", "no such memory")
            fields = {**patch, "pinned": int(patch["pinned"])} if "pinned" in patch else dict(patch)
            if "text" in fields:
                fields["provenance"] = "user_stated"  # the person wrote it now
            view = mem.update_memory(tx, args.memory_id, **fields) if fields else mem.memory_view(row)
            return {"memory": view}, []

        result = self._command("UpdateMemory", args, apply)
        activated = patch.get("status") == "active" or "text" in patch
        if activated and not from_shell and not result["duplicate"]:
            # Settings can't be told apart from other programs (§13.7): a memory made active or
            # rewritten outside the popup is announced, since it goes into every future prompt.
            self._notify("Mei will now remember", result["memory"]["text"])
        return result

    def forget_memory(self, args: ForgetMemoryArgs) -> dict:
        def apply(tx: Tx) -> tuple[dict, list[str]]:
            if args.everything:
                ids = [r["id"] for r in tx.execute("SELECT id FROM memories").fetchall()]
                for memory_id in ids:
                    mem.delete_memory(tx, memory_id)
                return {"forgotten": len(ids)}, []
            if not args.memory_id or not mem.delete_memory(tx, args.memory_id):
                raise ProtocolError("NotFound", "no such memory")
            return {"forgotten": 1}, []

        return self._command("ForgetMemory", args, apply)

    def list_grants(self) -> dict:
        return {"grants": [agent.grant_view(g) for g in agent.persistent_grants(self.store)]}

    def revoke_grant(self, args: RevokeGrantArgs) -> dict:
        def apply(tx: Tx) -> tuple[dict, list[str]]:
            return {"grant_id": args.grant_id, "revoked": agent.revoke_grant(tx, args.grant_id)}, []

        return self._command("RevokeGrant", args, apply)

    def delete_conversation(self, args: ConversationCommandArgs) -> dict:
        def apply(tx: Tx) -> tuple[dict, list[str]]:
            if repo.blocking_task(tx, args.conversation_id) is not None:
                raise ProtocolError("Busy", "stop the reply before deleting this conversation")
            repo.delete_conversation(tx, args.conversation_id)
            return {"conversation_id": args.conversation_id, "deleted": True}, []

        result = self._command("DeleteConversation", args, apply)
        self._delete_files(args.conversation_id)
        return result

    def _delete_files(self, conversation_id: str) -> None:
        """What a conversation left on disk: backups of files its tasks overwrote, command output,
        and its workspace."""
        for folder in (backups_dir(self.env, conversation_id), self.env.artifacts(conversation_id),
                       self.env.workspace(conversation_id)):
            try:
                shutil.rmtree(folder)
            except FileNotFoundError:
                pass
            except OSError as e:  # the conversation is gone either way; say what's left behind
                log.warning("couldn't delete %s: %s", folder, e)

    def update_config(self, args: UpdateConfigArgs) -> dict:
        revision, current = repo.get_config(self.store)
        if args.revision == revision and current == args.config:
            # Nothing changes, so nothing is written or announced. Clients that re-push on
            # config.changed would otherwise feed each other forever.
            return {"revision": revision, "changed": False}
        with self.store.tx() as tx:
            revision = repo.put_config(tx, args.revision, args.config)
        self._publish(tx.events)
        if args.config.privacy != current.privacy:
            self.apply_retention()
        loosened = _loosened(current, args.config)
        if loosened:
            self._notify("Mei's settings changed", loosened)
        return {"revision": revision, "changed": True}

    def _notify(self, title: str, body: str) -> None:
        """A desktop notification, so a change made by any program is seen (§13.7)."""
        notifier = self.env.notifier
        if notifier is None:
            log.warning("%s: %s (no notifications available)", title, body)
            return

        async def send() -> None:
            try:
                await notifier.notify(title, body)
            except Exception as e:  # the setting is saved either way; say so in the log
                log.warning("couldn't show the notification %r: %s", title, e)

        asyncio.get_running_loop().create_task(send())

    def apply_retention(self, now: int | None = None) -> int:
        """Delete conversations untouched for longer than the user's retention setting (§14.4).

        Conversations with a task still in progress are left for the next pass.
        """
        _revision, config = repo.get_config(self.store)
        days = config.privacy.conversation_retention_days
        if days is None:
            return 0
        cutoff = (now if now is not None else now_ms()) - days * 86_400_000
        rows = self.store.read("SELECT id FROM conversations WHERE updated_at < ?", (cutoff,))
        deleted = 0
        for row in rows:
            with self.store.tx() as tx:
                if repo.blocking_task(tx, row["id"]) is not None:
                    continue
                repo.delete_conversation(tx, row["id"])
            self._publish(tx.events)
            self._delete_files(row["id"])
            deleted += 1
        if deleted:
            log.info("retention: deleted %d conversation%s older than %d days", deleted, "s" if deleted != 1 else "", days)
        return deleted

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
        self._publish(tx.events)
        for task_id in to_start:
            self._schedule(task_id)
        return {**result, "duplicate": False}

    # ── Running ─────────────────────────────────────────────────────────────

    def _schedule(self, task_id: str) -> None:
        if task_id in self._runners or self._shutting_down:
            return
        runner = asyncio.get_running_loop().create_task(self._run(task_id), name=f"task-{task_id}")
        self._runners[task_id] = runner
        runner.add_done_callback(lambda _t: self._runners.pop(task_id, None))

    async def _run(self, task_id: str) -> None:
        try:
            async with self._slots:
                row = repo.get_task(self.store, task_id)
                if row is None or S(row["state"]) not in (S.ACCEPTED, S.INTERRUPTED, S.RUNNING):
                    return
                if S(row["state"]) != S.RUNNING:
                    with self.store.tx() as tx:
                        repo.set_task_state(tx, task_id, S.RUNNING)
                    self._publish(tx.events)
                await self.loop.run(task_id)
        except asyncio.CancelledError:
            # Stopped while waiting for a slot: the loop never ran, so settle a stop here.
            if not self._shutting_down:
                self._settle_cancel(task_id)
            raise


_PRESET_ORDER = ("cautious", "balanced", "hands_off")
_CLOUD_ORDER = ("never", "pointed", "always")


def _loosened(before: Config, after: Config) -> str:
    """What a config change relaxed, in words, or "" if nothing was."""
    changes = []
    if _PRESET_ORDER.index(after.approvals.preset) > _PRESET_ORDER.index(before.approvals.preset):
        changes.append("more actions now go ahead without asking")
    if _CLOUD_ORDER.index(after.privacy.cloud_files) > _CLOUD_ORDER.index(before.privacy.cloud_files):
        changes.append("more file contents may now go to cloud models")
    if after.clients.external_input and not before.clients.external_input:
        changes.append("other programs may now give it requests")
    if after.voice.enabled and after.voice.wake_word and not (before.voice.enabled and before.voice.wake_word):
        changes.append("it now listens for “Hey Mei” all the time")
    if after.voice.stt != "local" and after.voice.stt != before.voice.stt:
        changes.append(f"what you say to it now goes to {after.voice.stt.capitalize()} to be written down")
    for provider_id, settings in after.providers.items():
        old_url = before.providers[provider_id].url if provider_id in before.providers else ""
        if settings.url.strip() and settings.url.strip() != old_url.strip():
            changes.append(f"{provider_id} conversations now go to {_host(settings.url)}")
    if not changes:
        return ""
    return "Its settings changed: " + "; ".join(changes) + ". If you didn't do this, check Mei's Settings."


def _host(url: str) -> str:
    try:
        return urlsplit(url.strip()).hostname or url.strip()
    except ValueError:
        return url.strip()


def _valid_answer(spec: dict, value):
    choices, fields = spec.get("choices") or [], spec.get("fields") or []
    if fields:
        if not isinstance(value, dict):
            raise ProtocolError("InvalidArgument", "this question takes a form")
        names = {f["name"]: f for f in fields}
        unknown = set(value) - set(names)
        if unknown:
            raise ProtocolError("InvalidArgument", f"unknown fields: {sorted(unknown)}")
        for name, answer in value.items():
            options = names[name].get("options") or []
            if names[name].get("kind") == "select" and options and answer not in options:
                raise ProtocolError("InvalidArgument", f"{name} must be one of {options}")
        return value
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_INPUT_CHARS:
        raise ProtocolError("InvalidArgument", "the answer must be text")
    if choices and value not in choices:
        raise ProtocolError("InvalidArgument", f"the answer must be one of {choices}")
    return value.strip()


def _attached(attachment: Attachment | None) -> dict | None:
    """The message's metadata for what came with it (§18.4), or None when nothing did. Dropped files
    are absolute paths as the Shell got them, each once, and carry nothing else."""
    if attachment is None:
        return None
    if attachment.kind != "files":
        if attachment.paths:
            raise ProtocolError("InvalidArgument", "only dropped files carry paths")
        if not (attachment.text.strip() or attachment.window_title.strip()):
            return None
        return {"attachment": msgspec.to_builtins(attachment)}
    if attachment.text or attachment.window_title or attachment.app_id:
        raise ProtocolError("InvalidArgument", "dropped files carry only their paths")
    paths = list(dict.fromkeys(attachment.paths))
    if any("\0" in p or not os.path.isabs(p) or os.path.normpath(p) != p for p in paths):
        raise ProtocolError("InvalidArgument", "dropped files must be absolute paths")
    if not paths:
        return None
    return {"attachment": msgspec.to_builtins(msgspec.structs.replace(attachment, paths=paths))}


def _taint(tx: Tx, task_id: str, attached: dict) -> None:
    """Others wrote the attached text: the task has read untrusted content, as after reading a file.
    Dropped files are only pointed at; reading one later taints the task as any read does."""
    if attached["attachment"]["kind"] != "files":
        tx.execute("UPDATE tasks SET tainted = 1 WHERE id = ?", (task_id,))
