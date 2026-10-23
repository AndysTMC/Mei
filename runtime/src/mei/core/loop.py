"""The agent loop (§8.2): model → decide → act → record, until the task waits or ends.

Waiting is a stored state, not a coroutine: an approval, a question, or a restart ends the run, and
the next run finds the open batch and continues at its cursor. The model is called again only once
every action of a batch has a terminal state and a durable result (invariant 3), and it never sees
an observation before that observation is stored (invariant 5).
"""

import asyncio
import base64
import datetime
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import msgspec

from mei.capabilities.base import ActionContext, ActionResult, Capability, CapabilityError, CheckResult, Env
from mei.capabilities.computer import HANDOFF_DONE, HANDOFF_SKIP
from mei.capabilities.registry import Registry
from mei.core.states import ACTION_TERMINAL, TERMINAL, Disposition, Execution, TaskState, Verification
from mei.obs import redact
from mei.protocol import Envelope, ProviderConfig
from mei.providers.base import IncompleteResponse, Provider, ProviderError
from mei.providers.factory import label_of
from mei.capabilities.catalog import COMPUTER_TOOLS, MEMORY_TOOLS
from mei.store import agent, repo
from mei.store import memory as mem
from mei.store.db import Store

from . import context, decide, ending, finish, ledger, memories, remember
from .ending import InFlight
from .streaming import CALL_TIMEOUT_S, Reply, Stream, Streamer

log = logging.getLogger("mei.loop")
BUSY_POLL_S = 1.0
E, S, V = Execution, TaskState, Verification
MAX_ACTION_S = 600.0
MORE_CALLS = 25
MORE_TIME_MS = 30 * 60 * 1000
REPEAT_TEXT = ("Refused: you've already made this exact call twice. Don't repeat it; reconsider the approach, "
               "or ask the person with ask_user.")


class Crash(BaseException):
    """Test hook: the runtime dies at a named boundary (not an Exception, so nothing catches it)."""


@dataclass
class Deps:
    store: Store
    publish: Callable[[list[Envelope]], None]
    streamer: Streamer
    make_provider: Callable[[ProviderConfig], Awaitable[Provider]]
    registry: Registry
    env: Env
    boundary: Callable[[str], None] = field(default=lambda _name: None)
    now: Callable[[], datetime.datetime] = field(default=lambda: datetime.datetime.now(datetime.UTC))


class TaskLoop:
    def __init__(self, deps: Deps) -> None:
        self.d = deps

    async def run(self, task_id: str) -> None:
        """Drive a RUNNING task until it waits or ends. Re-raises CancelledError after settling."""
        flight = InFlight()
        try:
            await self._drive(task_id, flight)
        except asyncio.CancelledError:
            ending.stopped(self.d.store, self.d.publish, task_id, flight)
            raise
        except IncompleteResponse as e:  # cut off: keep it and let them resume
            ending.failed(self.d.store, self.d.publish, task_id, flight, S.INTERRUPTED, redact(str(e)))
        except ProviderError as e:
            ending.failed(self.d.store, self.d.publish, task_id, flight, S.FAILED, redact(str(e)))
        except TimeoutError:
            ending.failed(self.d.store, self.d.publish, task_id, flight, S.FAILED,
                          f"no complete reply within {int(CALL_TIMEOUT_S)} s")
        except Exception:
            log.exception("task failed", extra={"task_id": task_id})
            ending.failed(self.d.store, self.d.publish, task_id, flight, S.FAILED,
                          "internal error (see the Mei runtime log)")

    async def _drive(self, task_id: str, flight: InFlight) -> None:
        while True:
            task = repo.get_task(self.d.store, task_id)
            if S(task["state"]) != S.RUNNING:
                return
            batch = agent.open_batch(self.d.store, task_id)
            if batch is not None:
                if not await self._run_batch(task, batch, flight):
                    return
                continue
            if self._ask_to_continue(task):
                return
            await self._model_step(task, flight)

    # ── Model ───────────────────────────────────────────────────────────────

    async def _model_step(self, task, flight: InFlight) -> None:
        store = self.d.store
        cfg = msgspec.convert(json.loads(task["provider"]), ProviderConfig)
        _revision, config = repo.get_config(store)
        seen = ledger.last_ordinal(store, task["conversation_id"])
        recalled: list[dict] = []
        earlier: list[dict] = []
        if config.memory.enabled:
            recalled = memories.recall(store, task, local_only_ok=not context.is_cloud(cfg))
            earlier = memories.episodes(store, task)
        request = context.build(context.Inputs(
            store, self.d.env, self.d.registry, config.privacy, cfg, self.d.now(), memories=tuple(recalled),
            episodes=tuple(earlier), hidden_tools=hidden_tools(config)), task)
        label = {"id": cfg.id, "label": label_of(cfg), "model": cfg.model}
        with store.tx() as tx:
            turn = repo.begin_turn(tx, task["id"], store.epoch, label)
        self.d.publish(tx.events)
        flight.stream = Stream(task["conversation_id"], task["id"], turn["id"], turn["message_id"])
        provider = await self.d.make_provider(cfg)
        self.d.boundary("model_call")
        reply = await self.d.streamer.call(provider, request, flight.stream)
        self._commit_reply(task, turn, reply, label, seen)
        flight.stream = None
        self.d.boundary("reply_committed")

    def _commit_reply(self, task, turn: dict, reply: Reply, label: dict, seen: int) -> None:
        store = self.d.store
        metadata = {**label, "duration_ms": reply.duration_ms}
        if reply.usage is not None:
            metadata["tokens"] = {"input": reply.usage.input_tokens, "output": reply.usage.output_tokens}
        if reply.tools_dropped:
            metadata["tools_dropped"] = True
        calls = [{"id": c.id, "name": c.name, "arguments": c.arguments, "signature": c.signature} for c in reply.calls]
        replay = {"format": reply.replay.format, "data": reply.replay.data} if reply.replay else None
        taskd = repo.task_dict(task)
        with store.tx() as tx:
            message = repo.add_message(tx, task["conversation_id"], "assistant", reply.text, task_id=task["id"],
                                       thinking=reply.thinking or None, metadata=metadata,
                                       message_id=turn["message_id"], tool_calls=calls or None, replay=replay)
            repo.finish_turn(tx, turn["id"], "done")
            tx.execute("UPDATE tasks SET model_calls = model_calls + 1, active_ms = active_ms + ? WHERE id = ?",
                       (reply.duration_ms, task["id"]))
            if calls:
                agent.create_batch(tx, taskd, message["id"], calls, seen)
            elif ledger.steer_pending(tx, task["id"], seen):
                pass  # the person wrote while the model answered: go round again with their message
            elif not ledger.mutated(tx, task["id"]):
                final = repo.set_task_state(tx, task["id"], S.COMPLETED)  # an answer: no outcome to claim
                repo.finished_event(tx, final)
            elif task["nudges"] == 0:
                repo.add_message(tx, task["conversation_id"], "system", finish.NUDGE, task_id=task["id"])
                tx.execute("UPDATE tasks SET nudges = nudges + 1 WHERE id = ?", (task["id"],))
            else:
                checked = [finish.Checked(i, c.get("text", ""), c.get("check"), None)
                           for i, c in enumerate(json.loads(task["plan"]).get("criteria") or [])]
                finish.complete(tx, taskd, finish.outcome(checked, None, note="the model didn't report against "
                                                                               "its criteria"), text="")
        self.d.publish(tx.events)

    def _ask_to_continue(self, task) -> bool:
        over_calls = task["model_calls"] >= task["call_budget"]
        if not over_calls and task["active_ms"] < task["time_budget_ms"]:
            return False
        question = (f"Mei has taken {task['model_calls']} steps on this task. Keep going?" if over_calls else
                    f"Mei has worked on this for {task['active_ms'] // 60000} minutes. Keep going?")
        with self.d.store.tx() as tx:
            agent.create_input_request(tx, repo.task_dict(task), "continue",
                                       {"question": question, "choices": ["Keep going", "Stop"], "fields": []})
            repo.set_task_state(tx, task["id"], S.WAITING_INPUT)
        self.d.publish(tx.events)
        return True

    # ── Batches ─────────────────────────────────────────────────────────────

    async def _run_batch(self, task, batch, flight: InFlight) -> bool:
        """Work through the batch from its cursor. False: the task now waits or has ended."""
        store = self.d.store
        for position in range(batch["cursor"], batch["size"]):
            task = repo.get_task(store, task["id"])
            if S(task["state"]) != S.RUNNING:
                return False
            action = store.read_one("SELECT * FROM actions WHERE batch_id = ? AND position = ?", (batch["id"], position))
            state = E(action["execution"])
            if state in ACTION_TERMINAL:
                continue
            if state in (E.PROPOSED, E.AUTHORIZED) and ledger.steer_pending(store, task["id"], batch["seen_ordinal"]):
                with store.tx() as tx:
                    ledger.skip_rest(tx, repo.task_dict(task), batch["id"], "the person sent a new message first")
                self.d.publish(tx.events)
                return True
            if state == E.PROPOSED:
                state = self._decide(task, batch, action)
            if state == E.AWAITING_APPROVAL:
                return False
            if state == E.IN_DOUBT:
                if not await self._settle_in_doubt(task, agent.get_action(store, action["id"]), flight):
                    return False
                continue
            if state == E.AUTHORIZED and not await self._authorized(task, agent.get_action(store, action["id"]), flight):
                return False
        return True

    def _own_messages(self, task) -> list:
        """The person's messages in this task: its request and any steers, not earlier tasks."""
        return self.d.store.read(
            "SELECT content, metadata FROM messages WHERE role = 'user' AND (id = ? OR task_id = ?) ORDER BY ordinal",
            (task["input_message_id"], task["id"]))

    def _own_words(self, task) -> list[str]:
        return [r["content"] for r in self._own_messages(task)]

    def _seen(self, task) -> decide.Seen:
        """The person's words in this task, what they told Mei to remember that this task recalled
        (§17.5), and what Mei has read in it. What they attached is content others wrote (§18.4)."""
        own = self._own_messages(task)
        texts = [r["content"] for r in own] + memories.stated(self.d.store, task)
        rows = self.d.store.read("SELECT a.result, m.content FROM actions a JOIN messages m ON m.action_id = a.id "
                                 "WHERE a.task_id = ? AND a.result IS NOT NULL", (task["id"],))
        attached = [a for a in map(context.attachment_of, own) if a]
        content = [a.get("text", "") for a in attached]
        other = [a.get("window_title", "") for a in attached]
        for r in rows:
            result = json.loads(r["result"])
            if result.get("trust") == "untrusted":
                (content if result.get("data_class") in ("file_content", "screen") else other).append(r["content"])
        return decide.Seen(texts, content, other, workspace=self.d.env.workspace(task["conversation_id"]))

    def _proposal(self, task, action) -> decide.Proposal:
        cfg = msgspec.convert(json.loads(task["provider"]), ProviderConfig)
        _revision, config = repo.get_config(self.d.store)
        cap = self.d.registry.by_wire(action["tool"])
        if cap is not None and cap.name in hidden_tools(config):  # offered or not, a turned-off tool doesn't run
            raise decide.Refused(f"{action['tool']} is turned off in Mei's Settings.")
        proposal = decide.prepare(self.d.registry, self.d.env, action, self._seen(task))
        return decide.for_provider(proposal, cloud=context.is_cloud(cfg), cloud_files=config.privacy.cloud_files)

    def _decide(self, task, batch, action) -> Execution:
        store, env = self.d.store, self.d.env
        taskd = repo.task_dict(task)
        why = store.read_one("SELECT content FROM messages WHERE id = ?", (batch["message_id"],))["content"]
        try:
            proposal = self._proposal(task, action)
        except decide.Refused as e:
            with store.tx() as tx:
                ledger.finish_action(tx, taskd, action, E.REJECTED, str(e), is_error=True, error=str(e)[:500])
            self.d.publish(tx.events)
            return E.REJECTED
        fields = {"capability": proposal.cap.name, "version": proposal.cap.version, "params": proposal.canonical,
                  "params_hash": proposal.params_hash, **_judged_fields(proposal),
                  "reason": why[:decide.MAX_REASON_CHARS]}
        if not proposal.cap.meta and decide.repeated(store, task["id"], action["id"], proposal.cap.name,
                                                     proposal.params_hash):
            return self._refuse_repeat(task, batch, action, fields)
        _revision, config = repo.get_config(store)
        d = decide.judge(store, env, task, proposal, config.approvals.preset)
        fields |= {"decision": d.decision, "decision_reason": d.reason, "policy_version": d.version,
                   "grant_id": d.grant_id}
        with store.tx() as tx:
            if d.decision == "allow":
                agent.update_action(tx, action["id"], E.AUTHORIZED, **fields)
            elif d.decision == "deny":
                ledger.finish_action(tx, taskd, action, E.POLICY_DENIED, decide.refusal_text(d), is_error=True,
                                     error=d.reason, **fields)
            else:
                agent.update_action(tx, action["id"], E.AWAITING_APPROVAL, **fields)
                ledger.request_approval(tx, taskd, action["id"], proposal.params_hash, self._card(task, proposal, d, why))
        self.d.publish(tx.events)
        self.d.boundary("decided")
        return {"allow": E.AUTHORIZED, "deny": E.POLICY_DENIED}.get(d.decision, E.AWAITING_APPROVAL)

    def _refuse_repeat(self, task, batch, action, fields: dict) -> Execution:
        taskd = repo.task_dict(task)
        with self.d.store.tx() as tx:
            ledger.finish_action(tx, taskd, action, E.REJECTED, REPEAT_TEXT, is_error=True, error="repeated", **fields)
            tx.execute("UPDATE tasks SET guard_trips = guard_trips + 1 WHERE id = ?", (task["id"],))
            if task["guard_trips"] + 1 >= 2:  # the second trip ends the task (§8.2)
                ledger.skip_rest(tx, taskd, batch["id"], "Mei stopped the task")
                final = repo.set_task_state(tx, task["id"], S.BLOCKED,
                                            error="Mei kept repeating the same step, so it stopped.")
                repo.finished_event(tx, final)
        self.d.publish(tx.events)
        return E.REJECTED

    def _card(self, task, proposal: decide.Proposal, d, why: str) -> dict:
        cfg = msgspec.convert(json.loads(task["provider"]), ProviderConfig)
        return decide.card(self.d.env, proposal, d, why=why, read_from=self._read_from(task["id"]),
                           provider_label=label_of(cfg), cloud=context.is_cloud(cfg))

    async def _recheck(self, task, action) -> bool:
        """Just before it runs, look again at what it would touch: a symlink swapped while the card was
        up must not carry the approval somewhere else (invariant 10). False: it no longer runs now."""
        try:
            proposal = self._proposal(task, action)
        except decide.Refused:
            return True  # what it names is gone; the capability itself reports that
        if [msgspec.to_builtins(s) for s in proposal.subjects] == json.loads(action["resources"]):
            return True
        _revision, config = repo.get_config(self.d.store)
        d = decide.judge(self.d.store, self.d.env, task, proposal, config.approvals.preset)
        taskd = repo.task_dict(task)
        with self.d.store.tx() as tx:
            fields = {**_judged_fields(proposal), "decision": d.decision, "decision_reason": d.reason}
            if d.decision == "deny":
                ledger.finish_action(tx, taskd, action, E.POLICY_DENIED, decide.refusal_text(d), is_error=True,
                                     error=d.reason, **fields)
            elif d.decision == "ask" or action["approval_id"]:  # what was approved isn't what it would touch now
                ledger.reask(tx, taskd, action, card=self._card(task, proposal, d, action["reason"]), **fields)
            else:
                tx.execute("UPDATE actions SET resources = ?, effects = ?, description = ? WHERE id = ?",
                           (json.dumps(fields["resources"]), json.dumps(fields["effects"]), fields["description"],
                            action["id"]))
        self.d.publish(tx.events)
        return d.decision == "allow" and not action["approval_id"]

    def _read_from(self, task_id: str) -> list[str]:
        rows = self.d.store.read("SELECT result FROM actions WHERE task_id = ? AND execution = 'SUCCEEDED'", (task_id,))
        sources: list[str] = []
        for r in rows:
            sources += json.loads(r["result"]).get("sources", []) if r["result"] else []
        return list(dict.fromkeys(sources))

    # ── Acting ──────────────────────────────────────────────────────────────

    async def _authorized(self, task, action, flight: InFlight) -> bool:
        cap = self.d.registry.get(action["capability"])
        params = self.d.registry.decode(cap, action["params"])
        if cap.meta:
            return await self._meta(task, action, cap, params)
        if action["approval_id"]:  # invariants 2 and 10: the approval must still match these exact params
            approval = agent.get_approval(self.d.store, action["approval_id"])
            if approval is None or approval["state"] != "allowed" or approval["params_hash"] != action["params_hash"]:
                with self.d.store.tx() as tx:
                    ledger.reask(tx, repo.task_dict(task), action)
                self.d.publish(tx.events)
                return False
        elif action["decision"] != "allow":
            raise RuntimeError(f"action {action['id']} is authorized without a decision")
        if not await self._recheck(task, action):
            return S(repo.get_task(self.d.store, task["id"])["state"]) == S.RUNNING  # denied: go on; asked: wait
        if not await self._until_free(task, cap, params):
            return False
        await self._execute(task, agent.get_action(self.d.store, action["id"]), cap, params, flight)
        return True

    async def _until_free(self, task, cap: Capability, params) -> bool:
        """While the capability says the world is busy (the person took over the pointer), the task waits
        in WAITING_RESOURCE; Resume goes on at once. False: it was stopped meanwhile."""
        store, task_id = self.d.store, task["id"]
        ctx = ActionContext(self.d.env, "", task["conversation_id"], task_id)
        why = await cap.busy(params, ctx)
        if not why:
            return True
        with store.tx() as tx:
            repo.set_task_state(tx, task_id, S.WAITING_RESOURCE, error=why)
        self.d.publish(tx.events)
        while True:
            await asyncio.sleep(BUSY_POLL_S)
            state = S(repo.get_task(store, task_id)["state"])
            if state == S.RUNNING:  # the person pressed Resume
                return True
            if state != S.WAITING_RESOURCE:
                return False
            if not await cap.busy(params, ctx):
                with store.tx() as tx:
                    repo.set_task_state(tx, task_id, S.RUNNING)
                self.d.publish(tx.events)
                return True

    async def _meta(self, task, action, cap: Capability, params) -> bool:
        store, taskd = self.d.store, repo.task_dict(task)
        if cap.name == "plan.update":
            with store.tx() as tx:
                finish.save_plan(tx, taskd, action, params)
            self.d.publish(tx.events)
            return True
        if cap.name == "ask_user":
            with store.tx() as tx:
                finish.ask(tx, taskd, action, params)
            self.d.publish(tx.events)
            return False
        if cap.name == "memory.save":
            self._remember(task, action, params)
            return True
        with store.tx() as tx:  # task.finish
            repo.set_task_state(tx, task["id"], S.VERIFYING)
            agent.update_action(tx, action["id"], E.STARTED, epoch=store.epoch)
        self.d.publish(tx.events)
        task = repo.get_task(store, task["id"])
        checked = await finish.run_checks(json.loads(task["plan"]), self.d.env)
        failed = [c for c in checked if c.result is not None and c.result.status == "failed"]
        seen = store.read_one("SELECT seen_ordinal FROM batches WHERE id = ?", (action["batch_id"],))["seen_ordinal"]
        with store.tx() as tx:
            if ledger.steer_pending(tx, task["id"], seen):  # they wrote while Mei checked: read it first
                ledger.finish_action(tx, taskd, action, E.SUCCEEDED, finish.STEERED, is_error=False,
                                     result={"ok": True, "summary": "Paused finishing to read your message"})
                repo.set_task_state(tx, task["id"], S.RUNNING)
            elif failed and task["finish_attempts"] == 0 and not params.blocked:
                ledger.finish_action(tx, taskd, action, E.SUCCEEDED, finish.failures_text(failed), is_error=False,
                                     result={"ok": True, "summary": "Checked the result: something isn't right yet"})
                tx.execute("UPDATE tasks SET finish_attempts = finish_attempts + 1 WHERE id = ?", (task["id"],))
                repo.set_task_state(tx, task["id"], S.RUNNING)
            else:
                finish.finished(tx, repo.task_dict(task), action, params, checked)
        self.d.publish(tx.events)
        return S(repo.get_task(store, task["id"])["state"]) not in TERMINAL

    def _remember(self, task, action, params) -> None:
        """memory.save: where the words came from decides what it becomes (core/remember.py)."""
        store, taskd = self.d.store, repo.task_dict(task)
        _revision, config = repo.get_config(store)
        verdict = remember.judge(params.text, self._own_words(task), tainted=bool(task["tainted"]),
                                 auto_save=config.memory.auto_save)
        with store.tx() as tx:
            agent.update_action(tx, action["id"], E.STARTED, epoch=store.epoch)
            if not config.memory.enabled or verdict.status == "refused":
                why = "memory is off in Mei's Settings" if not config.memory.enabled else verdict.reason
                ledger.finish_action(tx, taskd, action, E.FAILED, f"Not saved: {why}.", is_error=True, error=why)
            else:
                same = mem.find_same(tx, params.text)
                if same is not None:
                    saved = mem.memory_view(same)
                else:
                    saved = mem.add_memory(tx, params.text.strip(), provenance=verdict.provenance,
                                           status=verdict.status, task_id=task["id"],
                                           conversation_id=task["conversation_id"])
                note = ("Already remembered." if same else "Saved." if saved["status"] == "active"
                        else f"Kept for the person to review: {verdict.reason}.")
                ledger.finish_action(tx, taskd, action, E.SUCCEEDED, note, is_error=False,
                                     result={"ok": True, "summary": f"Remembered: {saved['text']}",
                                             "memory_id": saved["id"], "memory_status": saved["status"]})
        self.d.publish(tx.events)

    async def _execute(self, task, action, cap: Capability, params, flight: InFlight) -> None:
        store = self.d.store
        with store.tx() as tx:
            agent.update_action(tx, action["id"], E.STARTED, epoch=store.epoch)  # durable before any effect
        self.d.publish(tx.events)
        flight.action_id = action["id"]
        self.d.boundary("action_started")
        ctx = ActionContext(self.d.env, action["id"], task["conversation_id"], task["id"], _judged(action))
        timeout = min(cap.timeout_s, MAX_ACTION_S)
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(cap.run(params, ctx), timeout)
        except CapabilityError as e:
            result = ActionResult(ok=False, observation=e.message, error_class=e.error_class, summary=e.message)
        except TimeoutError:
            result = ActionResult(ok=False, observation=f"It didn't finish within {int(timeout)} s.",
                                  error_class="timeout", summary="Timed out")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("%s failed", cap.name, extra={"task_id": task["id"]})
            result = ActionResult(ok=False, observation="It failed inside Mei (see the Mei runtime log).",
                                  error_class="failed", summary="Failed")
        self.d.boundary("action_ran")
        if result.ok and result.handoff:
            self._hand_off(task, action, result.handoff)
            flight.action_id = None
            return
        check: CheckResult | None = None
        if result.ok:
            try:
                check = await cap.verify(params, result, ctx)
            except Exception as e:
                log.warning("checking %s failed: %s", cap.name, e, extra={"task_id": task["id"]})
                check = CheckResult(status="unverifiable", detail="the check itself failed")
        self._record(task, action, result, check, int((time.monotonic() - started) * 1000))
        flight.action_id = None
        self.d.boundary("action_recorded")

    def _hand_off(self, task, action, question: str) -> None:
        """A step only the person may do (§10.3: a password field): the action stays started, and the
        task waits for them to say Done (engine.answer_input finishes it)."""
        with self.d.store.tx() as tx:
            agent.create_input_request(tx, repo.task_dict(task), "handoff",
                                       {"question": question, "choices": [HANDOFF_DONE, HANDOFF_SKIP], "fields": []},
                                       action_id=action["id"])
            repo.set_task_state(tx, task["id"], S.WAITING_INPUT)
        self.d.publish(tx.events)

    def _record(self, task, action, result: ActionResult, check: CheckResult | None, elapsed_ms: int) -> None:
        mutating = (json.loads(action["effects"]) or {}).get("mutates", "no") != "no"
        observation = result.observation if result.ok else f"Error ({result.error_class or 'failed'}): {result.observation}"
        if check is not None and check.status == "failed":
            observation += f"\n(Mei checked afterwards: it didn't take effect. {check.detail})"
        stored = msgspec.to_builtins(result)
        stored.pop("observation")
        stored["images"] = self._keep_images(task, action, stored.pop("images"))
        if check is not None:
            stored["check"] = check.detail
        with self.d.store.tx() as tx:
            ledger.finish_action(tx, repo.task_dict(task), action, E.SUCCEEDED if result.ok else E.FAILED, observation,
                                 is_error=not result.ok, result=stored,
                                 verification=check.status if check else V.NOT_APPLICABLE,
                                 disposition=Disposition.CONFIRMED if result.ok and mutating else Disposition.NONE,
                                 error=None if result.ok else result.observation[:500])
            # Content others wrote (a document, a screen) taints the task; a folder listing doesn't.
            taints = result.trust == "untrusted" and result.data_class in ("file_content", "screen")
            tx.execute("UPDATE tasks SET active_ms = active_ms + ?, tainted = MAX(tainted, ?) WHERE id = ?",
                       (elapsed_ms, int(taints), task["id"]))
        self.d.publish(tx.events)

    def _keep_images(self, task, action, images: list[str]) -> list[str]:
        """Pictures go to the conversation's artifacts (deleted with it), not into the ledger."""
        paths = []
        folder = self.d.env.artifacts(task["conversation_id"])
        for i, data in enumerate(images[:2]):
            try:
                folder.mkdir(mode=0o700, parents=True, exist_ok=True)
                path = folder / f"{action['id']}-{i}.png"
                path.write_bytes(base64.b64decode(data, validate=True))
                paths.append(str(path))
            except (OSError, ValueError) as e:
                log.warning("couldn't keep a picture: %s", e, extra={"task_id": task["id"]})
        return paths

    async def _settle_in_doubt(self, task, action, flight: InFlight) -> bool:
        """An action that was running when Mei died (§15): re-run it if that's safe, else probe the
        world, else ask the person. False: now waiting for their answer."""
        cap = self.d.registry.get(action["capability"])
        params = self.d.registry.decode(cap, action["params"])
        if cap.meta:
            return await self._meta(task, action, cap, params)  # only task.finish can be mid-way; it reads, so redo it
        if cap.idempotent:
            await self._execute(task, action, cap, params, flight)
            return True
        try:
            disposition = await cap.probe(params, ActionContext(self.d.env, action["id"], task["conversation_id"], task["id"],
                                                                _judged(action)))
        except Exception as e:
            log.warning("probing %s failed: %s", cap.name, e, extra={"task_id": task["id"]})
            disposition = Disposition.UNKNOWN
        taskd = repo.task_dict(task)
        with self.d.store.tx() as tx:
            if disposition == Disposition.CONFIRMED:
                ledger.finish_action(tx, taskd, action, E.SUCCEEDED, f"Done before Mei restarted: {action['description']}.",
                                     is_error=False, disposition=Disposition.CONFIRMED,
                                     result={"ok": True, "summary": action["description"]})
            elif disposition == Disposition.NONE:
                ledger.finish_action(tx, taskd, action, E.FAILED, "Not done: Mei restarted before it ran. You can try "
                                     "it again.", is_error=True, disposition=Disposition.NONE, error="interrupted")
            else:
                ledger.ask_in_doubt(tx, taskd, action)
        self.d.publish(tx.events)
        return disposition != Disposition.UNKNOWN


def hidden_tools(config) -> frozenset[str]:
    """Tools a setting turns off: memory's while memory is off, computer use's until it's allowed."""
    return (frozenset() if config.memory.enabled else MEMORY_TOOLS) | \
        (frozenset() if config.computer.enabled else COMPUTER_TOOLS)


def _judged(action) -> dict[str, tuple[str, ...]]:
    """Each path role → the values policy recorded for it, in order: what the run may act on (fs_at.py)."""
    judged: dict[str, tuple[str, ...]] = {}
    for r in json.loads(action["resources"] or "[]"):
        if r.get("kind") == "path":
            judged[r["role"]] = (*judged.get(r["role"], ()), r["value"])
    return judged


def _judged_fields(proposal: decide.Proposal) -> dict:
    return {"effects": msgspec.to_builtins(proposal.effects),
            "resources": [msgspec.to_builtins(sub) for sub in proposal.subjects], "description": proposal.description}
