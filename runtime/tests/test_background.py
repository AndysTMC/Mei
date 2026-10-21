"""Background tasks (§18.4, Stage 4): the conversation list shows each task in progress, and the
runtime notifies by itself only while the Shell isn't attached to do it."""

import asyncio

from mei.core.states import TaskState
from mei.ipc.notices import Notices
from mei.protocol import TaskCommandArgs
from mei.store import repo

from agent_harness import Harness, call, put, turn

S = TaskState


class FakeNotifier:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    async def notify(self, title: str, body: str) -> int:
        if self.fail:
            raise RuntimeError("no notification server")
        self.sent.append((title, body))
        return 1


def trash_script() -> list[dict]:
    return [turn(call("fs_trash", path="~/Music/old.txt")), {"text": "Done."}]


async def test_the_list_shows_the_task_in_progress_until_it_ends(tmp_path):
    h = Harness(tmp_path, script=trash_script())
    put(h.env, "~/Music/old.txt")
    r = h.submit("tidy up my downloads")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    [listed] = repo.list_conversations(h.store)
    assert listed["active"] == S.WAITING_APPROVAL
    h.approve(r["task_id"])
    assert await h.until(r["task_id"]) == S.COMPLETED
    assert repo.list_conversations(h.store)[0]["active"] is None


async def test_without_the_shell_the_runtime_notifies_with_the_title_only(tmp_path):
    h = Harness(tmp_path, script=trash_script())
    put(h.env, "~/Music/old.txt")
    notifier = FakeNotifier()
    notices = Notices(notifier, lambda cid: repo.get_conversation(h.store, cid)["title"])
    r = h.submit("tidy up my downloads")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    h.approve(r["task_id"])
    assert await h.until(r["task_id"]) == S.COMPLETED
    notices.on_events(h.rec.events, shell_attached=True)
    await asyncio.sleep(0)
    assert notifier.sent == []
    notices.on_events(h.rec.events, shell_attached=False)
    await asyncio.sleep(0)
    title = repo.get_conversation(h.store, r["conversation_id"])["title"]
    assert notifier.sent == [("Mei needs your OK", title), ("Mei finished", title)]


async def test_a_stopped_task_raises_no_notice_and_a_failing_notifier_is_only_logged(tmp_path, caplog):
    h = Harness(tmp_path, script=trash_script())
    put(h.env, "~/Music/old.txt")
    r = h.submit("tidy up my downloads")
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    h.engine.cancel(TaskCommandArgs(command_id="stop", task_id=r["task_id"]))
    assert await h.until(r["task_id"]) == S.CANCELLED
    quiet = FakeNotifier()
    Notices(quiet, lambda _cid: "t").on_events(h.rec.events, shell_attached=False)
    Notices(FakeNotifier(fail=True), lambda _cid: "t").on_events(h.rec.events, shell_attached=False)
    await asyncio.sleep(0)
    assert quiet.sent == [("Mei needs your OK", "t")]  # the card, but nothing for the stop
    assert "couldn't show the notification" in caplog.text
