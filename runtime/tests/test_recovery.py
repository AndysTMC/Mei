"""Crash consistency (§15, §20): the runtime dies at each durable boundary of the loop; a new
runtime on the same store must reach the recovery table's outcome, and nothing runs twice."""

import asyncio

import pytest

from mei.capabilities.catalog import default_registry
from mei.core.engine import Engine
from mei.core.loop import Crash
from mei.core.states import Disposition, Execution, TaskState
from mei.protocol import TaskCommandArgs
from mei.store.db import Store

from agent_harness import Harness, Recorder, assert_provider_valid, call, fake_factory, put, turn

S, E = TaskState, Execution
MOVE = call("fs_move", source="~/Downloads/a.txt", destination="~/Documents/Filed/")
SCRIPT = [turn(MOVE), turn(MOVE), turn(call("task_finish", summary="Filed a.txt."))]
ASK = "move a.txt from Downloads to Documents/Filed"


class CrashOnce:
    def __init__(self, at: str) -> None:
        self.at = at
        self.fired = False

    def __call__(self, name: str) -> None:
        if name == self.at and not self.fired:
            self.fired = True
            raise Crash(name)


async def crashed(tmp_path, at: str) -> tuple[Harness, dict]:
    h = Harness(tmp_path, script=SCRIPT, boundary=CrashOnce(at))
    put(h.env, "~/Downloads/a.txt", "a")
    r = h.submit(ASK)
    async with asyncio.timeout(5):
        while r["task_id"] in h.engine._runners:
            await asyncio.sleep(0.01)
    assert h.engine.loop.d.boundary.fired, f"never reached {at}"
    h.store.close()
    return h, r


def restart(h: Harness) -> None:
    h.rec = Recorder()
    h.engine = Engine(Store(h.tmp / "mei"), h.rec, fake_factory, registry=default_registry(), env=h.env)
    h.engine.recover()


@pytest.mark.parametrize("at,first_move", [
    ("model_call", None),  # no reply was stored: nothing to settle
    ("reply_committed", (E.SUCCEEDED, Disposition.CONFIRMED)),  # proposed, decided after the restart
    ("decided", (E.SUCCEEDED, Disposition.CONFIRMED)),  # authorized by policy: kept
    ("action_started", (E.FAILED, Disposition.NONE)),  # in doubt; the probe sees it never happened
    ("action_ran", (E.SUCCEEDED, Disposition.CONFIRMED)),  # in doubt; the probe sees it happened: not re-run
    ("action_recorded", (E.SUCCEEDED, Disposition.CONFIRMED)),
])
async def test_kill_at_each_boundary(tmp_path, at, first_move):
    h, r = await crashed(tmp_path, at)
    restart(h)
    assert h.task(r["task_id"])["state"] == S.INTERRUPTED  # resumable, never silently re-sent
    if at in ("action_started", "action_ran"):
        assert h.actions(r["task_id"])[0]["execution"] == E.IN_DOUBT
    calls_before = len(h.requests())
    h.engine.resume(TaskCommandArgs(command_id="resume", task_id=r["task_id"]))
    assert await h.until(r["task_id"]) == S.COMPLETED
    moves = [a for a in h.actions(r["task_id"]) if a["capability"] == "fs.move"]
    if first_move is not None:
        assert (moves[0]["execution"], moves[0]["disposition"]) == first_move
    # Moved exactly once, whatever the boundary: never lost, never duplicated.
    assert h.env.path("~/Documents/Filed/a.txt").read_text() == "a" and not h.env.path("~/Downloads/a.txt").exists()
    assert len(h.requests()) > calls_before
    for request in h.requests():
        assert_provider_valid(request["turns"])


async def test_an_action_nobody_can_settle_is_asked_about(tmp_path, monkeypatch):
    from mei.capabilities.fs_write import FsMove
    h, r = await crashed(tmp_path, "action_started")

    async def unknown(self, p, ctx):
        return Disposition.UNKNOWN
    monkeypatch.setattr(FsMove, "probe", unknown)
    restart(h)
    h.engine.resume(TaskCommandArgs(command_id="resume", task_id=r["task_id"]))
    assert await h.until(r["task_id"]) == S.WAITING_INPUT
    h.answer(r["task_id"], "It didn't happen")
    assert await h.until(r["task_id"]) == S.COMPLETED
    assert h.actions(r["task_id"])[0]["execution"] == E.FAILED


async def test_a_one_time_approval_does_not_survive_a_restart(tmp_path):
    h = Harness(tmp_path, preset="cautious", script=SCRIPT)
    put(h.env, "~/Downloads/a.txt", "a")
    r = h.submit(ASK)
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    first = h.approval(r["task_id"])["id"]
    h.engine._schedule = lambda _task_id: None  # the runtime dies before the approved action starts
    h.approve(r["task_id"], scope="once")
    h.store.close()
    restart(h)
    assert h.task(r["task_id"])["state"] == S.WAITING_APPROVAL
    assert h.approval(r["task_id"])["id"] != first and h.env.path("~/Downloads/a.txt").exists()


async def test_a_task_grant_survives_a_restart(tmp_path):
    h = Harness(tmp_path, preset="cautious", script=SCRIPT)
    put(h.env, "~/Downloads/a.txt", "a")
    r = h.submit(ASK)
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    h.engine._schedule = lambda _task_id: None
    h.approve(r["task_id"], scope="task")
    h.store.close()
    restart(h)
    assert h.task(r["task_id"])["state"] == S.INTERRUPTED
    h.engine.resume(TaskCommandArgs(command_id="resume", task_id=r["task_id"]))
    assert await h.until(r["task_id"]) == S.COMPLETED
    assert h.env.path("~/Documents/Filed/a.txt").exists()


async def test_a_cancel_requested_before_the_crash_is_honoured(tmp_path):
    h, r = await crashed(tmp_path, "action_started")
    store = Store(h.tmp / "mei")
    with store.tx() as tx:
        tx.execute("UPDATE tasks SET state = 'CANCEL_REQUESTED' WHERE id = ?", (r["task_id"],))
    store.close()
    restart(h)
    assert h.task(r["task_id"])["state"] == S.CANCELLED
    action = h.actions(r["task_id"])[0]
    assert (action["execution"], action["disposition"]) == (E.CANCELLED, Disposition.UNKNOWN)
