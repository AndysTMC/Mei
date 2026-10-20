import asyncio
import json

import pytest

from mei.core import engine as engine_mod
from mei.core.engine import Engine
from mei.core.states import TERMINAL, TaskState
import msgspec

from mei.protocol import (Config, ConversationCommandArgs, ProtocolError, ProviderConfig, ProviderSettings, SubmitInputArgs,
                          TaskCommandArgs, UpdateConfigArgs)
from mei.providers.fake import FakeProvider
from mei.store import repo
from mei.store.db import Store

S = TaskState
REPLY = "The quick brown fox jumps over the lazy dog. " * 4


class Recorder:
    def __init__(self) -> None:
        self.events = []
        self.deltas = []

    def publish(self, events) -> None:
        self.events.extend(events)

    def publish_ephemeral(self, event) -> None:
        self.deltas.append(event)

    def types(self, task_id=None):
        return [e.type for e in self.events if task_id is None or e.task_id == task_id]


async def fake_factory(cfg: ProviderConfig):
    return FakeProvider(cfg.options)


def make_engine(path, *, max_concurrent=2, **options) -> tuple[Engine, Recorder]:
    rec = Recorder()
    eng = Engine(Store(path), rec, fake_factory, max_concurrent=max_concurrent)
    revision = eng.get_config()["revision"]
    eng.update_config(UpdateConfigArgs(revision, Config(active="fake", providers={"fake": ProviderSettings(
        options={"reply": REPLY, "chunk_chars": 6, "delay_ms": 5, **options})})))
    rec.events.clear()
    return eng, rec


async def wait_state(eng: Engine, task_id: str, states=TERMINAL, timeout=5.0) -> str:
    async with asyncio.timeout(timeout):
        while (state := repo.get_task(eng.store, task_id)["state"]) not in states:
            await asyncio.sleep(0.01)
    return state


async def wait_deltas(rec: Recorder, n: int, timeout=5.0) -> None:
    async with asyncio.timeout(timeout):
        while len(rec.deltas) < n:
            await asyncio.sleep(0.005)


def submit(eng, text="hello", command_id="c1", conversation_id=None) -> dict:
    return eng.submit_input(SubmitInputArgs(command_id=command_id, text=text, conversation_id=conversation_id))


async def test_turn_streams_and_completes(tmp_path):
    eng, rec = make_engine(tmp_path)
    r = submit(eng)
    assert await wait_state(eng, r["task_id"]) == S.COMPLETED
    assert rec.types() == ["conversation.created", "message.completed", "task.accepted", "task.state_changed",
                           "model.started", "message.completed", "task.state_changed", "task.finished"]
    seqs = [e.seq for e in rec.events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    chunks = [d.payload["chunk"] for d in rec.deltas]
    assert chunks == list(range(1, len(chunks) + 1))
    assert len(chunks) < len(REPLY) / 6  # coalesced: fewer deltas than provider chunks
    final = repo.history(eng.store, r["conversation_id"])[-1]
    assert final["role"] == "assistant" and final["content"] == REPLY
    assert "".join(d.payload["text"] for d in rec.deltas) == REPLY
    assert final["id"] == next(e for e in rec.events if e.type == "model.started").payload["message_id"]
    assert final["metadata"]["tokens"]["output"] == len(REPLY)


async def test_duplicate_command_returns_the_first_result(tmp_path):
    eng, rec = make_engine(tmp_path)
    first = submit(eng)
    again = submit(eng)
    assert again["duplicate"] and {k: again[k] for k in first if k != "duplicate"} == \
        {k: first[k] for k in first if k != "duplicate"}
    with pytest.raises(ProtocolError) as err:
        submit(eng, text="something else")
    assert err.value.name == "Conflict"
    assert eng.store.read_one("SELECT COUNT(*) AS n FROM tasks")["n"] == 1
    await wait_state(eng, first["task_id"])


async def test_new_input_while_answering_is_refused(tmp_path):
    eng, rec = make_engine(tmp_path, delay_ms=20)
    r = submit(eng)
    with pytest.raises(ProtocolError) as err:
        submit(eng, text="again", command_id="c2", conversation_id=r["conversation_id"])
    assert err.value.name == "Busy"
    await wait_state(eng, r["task_id"])
    second = submit(eng, text="again", command_id="c3", conversation_id=r["conversation_id"])
    assert await wait_state(eng, second["task_id"]) == S.COMPLETED


async def test_cancel_mid_stream_persists_request_first_and_keeps_a_draft(tmp_path):
    eng, rec = make_engine(tmp_path, delay_ms=15)
    r = submit(eng)
    await wait_deltas(rec, 2)
    res = eng.cancel(TaskCommandArgs(command_id="x1", task_id=r["task_id"]))
    assert res["state"] == S.CANCEL_REQUESTED
    assert await wait_state(eng, r["task_id"]) == S.CANCELLED
    changes = [e.payload["to"] for e in rec.events if e.type == "task.state_changed"]
    assert changes == [S.RUNNING, S.CANCEL_REQUESTED, S.CANCELLED]
    finished = next(e for e in rec.events if e.type == "task.finished")
    assert finished.payload["draft"]["text"] and REPLY.startswith(finished.payload["draft"]["text"])
    assert [m["role"] for m in repo.history(eng.store, r["conversation_id"])] == ["user"]


async def test_cancelling_a_queued_task_never_calls_the_provider(tmp_path):
    log = tmp_path / "calls.jsonl"
    eng, rec = make_engine(tmp_path / "db", max_concurrent=1, delay_ms=10, call_log=str(log))
    first = submit(eng, command_id="a")
    second = submit(eng, text="second", command_id="b")
    assert eng.cancel(TaskCommandArgs(command_id="x", task_id=second["task_id"]))["state"] == S.CANCELLED
    assert await wait_state(eng, first["task_id"]) == S.COMPLETED
    await asyncio.sleep(0.05)
    assert repo.get_task(eng.store, second["task_id"])["state"] == S.CANCELLED
    assert len(log.read_text().splitlines()) == 1


async def test_provider_failure_fails_the_task_with_its_message(tmp_path):
    eng, rec = make_engine(tmp_path, fail="quota exceeded")
    r = submit(eng)
    assert await wait_state(eng, r["task_id"]) == S.FAILED
    assert repo.get_task(eng.store, r["task_id"])["error"] == "quota exceeded"


async def test_transient_refusals_before_output_are_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_mod, "RETRY_BASE_S", 0.01)
    log = tmp_path / "calls.jsonl"
    eng, rec = make_engine(tmp_path / "db", busy_times=2, call_log=str(log))
    r = submit(eng)
    assert await wait_state(eng, r["task_id"]) == S.COMPLETED
    assert len(log.read_text().splitlines()) == 3
    assert repo.history(eng.store, r["conversation_id"])[-1]["content"] == REPLY


async def test_retries_give_up_after_the_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_mod, "RETRY_BASE_S", 0.01)
    log = tmp_path / "calls.jsonl"
    eng, rec = make_engine(tmp_path / "db", busy_times=5, call_log=str(log))
    r = submit(eng)
    assert await wait_state(eng, r["task_id"]) == S.FAILED
    assert len(log.read_text().splitlines()) == engine_mod.MAX_ATTEMPTS
    assert "overloaded" in repo.get_task(eng.store, r["task_id"])["error"]


async def test_failures_after_output_are_never_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_mod, "RETRY_BASE_S", 0.01)
    log = tmp_path / "calls.jsonl"
    eng, rec = make_engine(tmp_path / "db", fail="connection reset mid-reply", fail_retryable=True, call_log=str(log))
    r = submit(eng)
    assert await wait_state(eng, r["task_id"]) == S.FAILED
    assert len(log.read_text().splitlines()) == 1


async def test_shutdown_interrupts_instead_of_cancelling(tmp_path):
    eng, rec = make_engine(tmp_path, delay_ms=15)
    r = submit(eng)
    await wait_deltas(rec, 2)
    await eng.shutdown()
    assert repo.get_task(eng.store, r["task_id"])["state"] == S.INTERRUPTED


async def test_crash_recovery_interrupts_with_draft_and_never_resends(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_mod, "DRAFT_EVERY_S", 0.0)
    log = tmp_path / "calls.jsonl"
    eng, rec = make_engine(tmp_path / "db", delay_ms=15, call_log=str(log))
    r = submit(eng)
    queued = submit(eng, text="queued", command_id="c2")
    await wait_deltas(rec, 3)
    # Simulate a crash: the process dies mid-turn, nothing gets to finish its bookkeeping.
    monkeypatch.setattr(Engine, "_finish", lambda *a, **k: None)
    for runner in list(eng._runners.values()):
        runner.cancel()
    await asyncio.sleep(0.05)
    with eng.store.tx() as tx:  # a second task that was accepted but never started
        tx.execute("UPDATE tasks SET state = 'ACCEPTED' WHERE id = ?", (queued["task_id"],))
    eng.store.close()
    monkeypatch.undo()
    monkeypatch.setattr(engine_mod, "DRAFT_EVERY_S", 0.0)

    rec2 = Recorder()
    eng2 = Engine(Store(tmp_path / "db"), rec2, fake_factory)
    eng2.recover()
    interrupted = repo.get_task(eng2.store, r["task_id"])
    assert interrupted["state"] == S.INTERRUPTED
    finished = next(e for e in rec2.events if e.type == "task.finished" and e.task_id == r["task_id"])
    assert finished.payload["draft"]["text"] and REPLY.startswith(finished.payload["draft"]["text"])
    assert await wait_state(eng2, queued["task_id"]) == S.COMPLETED  # queued work restarts
    calls = [json.loads(line)["last_user"] for line in log.read_text().splitlines()]
    assert calls.count("hello") == 1  # the interrupted turn was not re-sent

    eng2.resume(TaskCommandArgs(command_id="r1", task_id=r["task_id"]))
    assert await wait_state(eng2, r["task_id"]) == S.COMPLETED
    assert [json.loads(line)["last_user"] for line in log.read_text().splitlines()].count("hello") == 2
    attempts = eng2.store.read("SELECT attempt, state FROM turns WHERE task_id = ? ORDER BY attempt", (r["task_id"],))
    assert [(t["attempt"], t["state"]) for t in attempts] == [(1, "lost"), (2, "done")]


async def test_new_message_supersedes_an_interrupted_task(tmp_path):
    eng, rec = make_engine(tmp_path, delay_ms=15)
    r = submit(eng)
    await wait_deltas(rec, 2)
    await eng.shutdown()
    eng._shutting_down = False
    nxt = submit(eng, text="moving on", command_id="c2", conversation_id=r["conversation_id"])
    assert repo.get_task(eng.store, r["task_id"])["state"] == S.CANCELLED
    assert await wait_state(eng, nxt["task_id"]) == S.COMPLETED


async def test_resume_only_applies_to_interrupted_tasks(tmp_path):
    eng, rec = make_engine(tmp_path)
    r = submit(eng)
    await wait_state(eng, r["task_id"])
    with pytest.raises(ProtocolError) as err:
        eng.resume(TaskCommandArgs(command_id="r", task_id=r["task_id"]))
    assert err.value.name == "Conflict"


async def test_delete_conversation_removes_its_history(tmp_path):
    eng, rec = make_engine(tmp_path)
    r = submit(eng)
    await wait_state(eng, r["task_id"])
    eng.delete_conversation(ConversationCommandArgs(command_id="d", conversation_id=r["conversation_id"]))
    assert repo.list_conversations(eng.store) == []
    assert repo.events_after(eng.store, 0, r["conversation_id"])[-1].type == "conversation.deleted"


async def test_an_unchanged_config_update_is_a_silent_no_op(tmp_path):
    eng, rec = make_engine(tmp_path)
    current = eng.get_config()
    same = UpdateConfigArgs(current["revision"], msgspec.convert(current["config"], Config))
    assert eng.update_config(same) == {"revision": current["revision"], "changed": False}
    assert rec.events == []
    changed = UpdateConfigArgs(current["revision"], Config(active="fake", providers={"fake": ProviderSettings(model="other")}))
    assert eng.update_config(changed)["changed"] is True
    assert [e.type for e in rec.events] == ["config.changed"]


async def test_refuses_input_without_a_provider(tmp_path):
    eng = Engine(Store(tmp_path), Recorder(), fake_factory)
    with pytest.raises(ProtocolError) as err:
        submit(eng)
    assert err.value.name == "Unsupported"


async def test_refuses_empty_input(tmp_path):
    eng, _ = make_engine(tmp_path)
    with pytest.raises(ProtocolError):
        submit(eng, text="   ")


def _age(eng: Engine, conversation_id: str, days: float) -> None:
    with eng.store.tx() as tx:
        tx.execute("UPDATE conversations SET updated_at = ? WHERE id = ?",
                   (repo.now_ms() - int(days * 86_400_000), conversation_id))


def _retention(eng: Engine, days: int | None) -> dict:
    revision, config = repo.get_config(eng.store)
    config.privacy.conversation_retention_days = days
    return eng.update_config(UpdateConfigArgs(revision, config))


async def test_retention_deletes_only_conversations_older_than_the_setting(tmp_path):
    eng, rec = make_engine(tmp_path)
    old = submit(eng, "old", "c1")
    await wait_state(eng, old["task_id"])
    new = submit(eng, "new", "c2")
    await wait_state(eng, new["task_id"])
    _age(eng, old["conversation_id"], 45)
    _age(eng, new["conversation_id"], 5)
    assert eng.apply_retention() == 0  # keep until I delete: the default
    rec.events.clear()

    _retention(eng, 30)  # choosing a retention period applies it at once
    ids = [c["id"] for c in repo.list_conversations(eng.store)]
    assert ids == [new["conversation_id"]]
    assert [e.payload for e in rec.events if e.type == "conversation.deleted"] == \
        [{"conversation_id": old["conversation_id"]}]
    assert eng.apply_retention() == 0


async def test_retention_leaves_a_conversation_that_is_still_answering(tmp_path):
    eng, _rec = make_engine(tmp_path, delay_ms=50)
    r = submit(eng)
    await wait_state(eng, r["task_id"], states={S.RUNNING})
    _age(eng, r["conversation_id"], 400)
    _retention(eng, 1)
    assert [c["id"] for c in repo.list_conversations(eng.store)] == [r["conversation_id"]]
    await wait_state(eng, r["task_id"])
    _age(eng, r["conversation_id"], 400)
    assert eng.apply_retention() == 1
