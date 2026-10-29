"""Every request gets a reply (§18.2). A task the runtime ended (stopped for repeating itself, stopped at
the step limit, stopped by the person, or failed) ended with no reply at all: the conversation showed the
person's message and nothing after it, voice said nothing (or a fixed "Sorry"), and the next request's
model saw two requests in a row with no word of how the first one ended."""

import pytest

from mei.core.states import TaskState
from mei.protocol import TaskCommandArgs

from agent_harness import Harness, call, put, turn

S = TaskState


def shown(h: Harness, conversation_id: str) -> list[dict]:
    return h.store.read("SELECT role, content, task_id FROM messages WHERE conversation_id = ? "
                        "AND role IN ('user', 'assistant') AND trim(content) != '' ORDER BY ordinal", (conversation_id,))


def ending(h: Harness, r: dict) -> str:
    """Mei's last word in the conversation, which must be about this task."""
    last = shown(h, r["conversation_id"])[-1]
    assert last["role"] == "assistant" and last["task_id"] == r["task_id"], shown(h, r["conversation_id"])
    return last["content"]


async def test_stopped_for_repeating_itself_says_so_after_what_it_said_on_the_way(tmp_path):
    """The owner's five tasks of 2026-10-26: "kept repeating", and nothing on screen."""
    same = turn(call("fs_list", path="~/Downloads"))
    h = Harness(tmp_path, script=[turn(call("fs_list", path="~/Downloads"), text="Let me look in Downloads."),
                                  same, same, same, same])
    r = h.submit("list Downloads")
    assert await h.until(r["task_id"]) == S.BLOCKED
    said = ending(h, r)
    assert said != "Let me look in Downloads." and "repeating" in said


async def test_stopped_at_the_step_limit(tmp_path):
    h = Harness(tmp_path, script=[turn(call("fs_list", path=f"~/Downloads/{n}")) for n in range(30)])
    for n in range(30):
        (h.env.home / "Downloads" / str(n)).mkdir()
    r = h.submit("list everything")
    assert await h.until(r["task_id"]) == S.WAITING_INPUT
    h.answer(r["task_id"], "Stop")
    assert await h.until(r["task_id"]) == S.BLOCKED
    assert "step limit" in ending(h, r)


async def test_a_failure_says_what_went_wrong(tmp_path):
    h = Harness(tmp_path, script=[{"text": "Looking now."}], fail="Gemini rejected the API key (HTTP 400)")
    r = h.submit("what's in Downloads?")
    assert await h.until(r["task_id"]) == S.FAILED
    said = ending(h, r)
    assert "couldn't" in said and "Gemini rejected the API key (HTTP 400)" in said
    # What streamed before it failed is kept, as the message that was streaming (voice has said it already).
    assert said.startswith("Looking now.")
    streamed = h.store.read_one("SELECT message_id FROM turns WHERE task_id = ?", (r["task_id"],))["message_id"]
    assert h.store.read_one("SELECT content FROM messages WHERE id = ?", (streamed,))["content"] == said


async def test_stopped_by_the_person(tmp_path):
    h = Harness(tmp_path, script=[turn(call("fs_trash", path="~/Music/old.txt"))])  # outside Downloads: a card
    put(h.env, "~/Music/old.txt")
    r = h.submit("tidy my files")  # not naming it: a card
    assert await h.until(r["task_id"]) == S.WAITING_APPROVAL
    assert h.engine.cancel(TaskCommandArgs(command_id="stop", task_id=r["task_id"]))["state"] == S.CANCELLED
    assert ending(h, r).startswith("Stopped")


async def test_an_answer_that_says_nothing_still_gets_a_reply(tmp_path):
    h = Harness(tmp_path, script=[{"text": ""}])
    r = h.submit("hello?")
    assert await h.until(r["task_id"]) == S.COMPLETED
    assert ending(h, r)


@pytest.mark.parametrize("script,state", [
    ([{"text": "Hello."}], S.COMPLETED),  # an answer
    ([turn(call("task_finish", summary="Couldn't find it.", blocked=True))], S.BLOCKED),  # the model's own stop
])
async def test_the_models_own_ending_is_the_only_reply(tmp_path, script, state):
    h = Harness(tmp_path, script=script)
    r = h.submit("find my tax form")
    assert await h.until(r["task_id"]) == state
    assert [m["role"] for m in shown(h, r["conversation_id"])] == ["user", "assistant"]


async def test_the_next_request_knows_how_the_stopped_one_ended(tmp_path):
    same = turn(call("fs_list", path="~/Downloads"))
    h = Harness(tmp_path, script=[same, same, same, same], scripts={"try again": [{"text": "OK."}]})
    r = h.submit("list Downloads")
    assert await h.until(r["task_id"]) == S.BLOCKED
    again = h.submit("try again", conversation_id=r["conversation_id"])
    await h.until(again["task_id"])
    turns = h.requests()[-1]["turns"]
    before = [t for t in turns if t["role"] == "assistant"]
    assert before and "repeating" in before[-1]["content"] and "What Mei did" in before[-1]["content"]


@pytest.mark.parametrize("script,fail,heard", [
    # Failed after saying something: the rest of that reply, how it ended, nothing said twice.
    ([{"text": "Looking now. "}], "Gemini: HTTP 503: overloaded",
     ["Looking now.", "I couldn't finish this.", "Gemini: HTTP 503: overloaded."]),
    # Stopped for repeating itself, which used to say nothing at all.
    ([turn(call("fs_list", path="~/Downloads"))] * 4, None, ["I stopped before finishing.", "I kept repeating the same step."]),
])
async def test_voice_says_how_it_ended_once(tmp_path, script, fail, heard):
    from mei.voice.replies import Replies
    h = Harness(tmp_path, script=script, **({"fail": fail} if fail else {}))
    r = h.submit("what's in Downloads?")
    await h.until(r["task_id"])
    said: list[str] = []
    replies = Replies(None, said.extend, lambda: None)
    replies.follow(r["task_id"])
    for event in h.rec.deltas + [e for e in h.rec.events if e.task_id == r["task_id"]]:
        (replies.delta if event.seq is None else replies.publish)(event)
    assert said == heard
