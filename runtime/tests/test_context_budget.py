"""A request fits what the model can take (decision 0037): the whole conversation and every result used to
be sent, with no limit on the total, so a long conversation or a task that read big files went past the
model's context (an error from a cloud model; a local one silently cut the start, the system prompt with it)."""

from mei.core import context
from mei.core.context import KEEP_WHOLE, SHORTENED_CHARS, fit
from mei.providers.base import ChatTurn, ToolCall

from agent_harness import Harness, call, turn

SYSTEM = ChatTurn("system", "You are Mei.")


def exchange(n: int, size: int = 1000) -> list[ChatTurn]:
    return [ChatTurn("user", f"question {n} " + "q" * size), ChatTurn("assistant", f"answer {n} " + "a" * size)]


def test_a_request_that_fits_is_sent_as_it_is():
    earlier = exchange(1) + exchange(2)
    current = [ChatTurn("user", "now this")]
    assert fit(SYSTEM, earlier, current, 100_000) == [SYSTEM, *earlier, *current]


def test_the_oldest_exchanges_go_first_whole_and_the_model_is_told():
    earlier = [t for n in range(10) for t in exchange(n)]
    current = [ChatTurn("user", "and now?")]
    sent = fit(SYSTEM, earlier, current, 6_000)
    assert sent[0] == SYSTEM and sent[-1].content.endswith("and now?")
    assert sum(len(t.content) for t in sent) <= 6_000
    first = sent[1]
    assert first.role == "user" and "earlier messages of this conversation are left out" in first.content
    assert "question 9" in "".join(t.content for t in sent) and "question 0" not in "".join(t.content for t in sent)
    assert all(a.role != b.role for a, b in zip(sent[1:], sent[2:]))  # no answer kept without its question


def test_a_task_that_read_too_much_keeps_its_newest_results_whole():
    """The related case: one task alone over the budget, with nothing earlier left to drop."""
    current = [ChatTurn("user", "read all the logs")]
    for n in range(8):
        current += [ChatTurn("assistant", "", tool_calls=(ToolCall(f"c{n}", "fs_read_text", "{}"),)),
                    ChatTurn("tool", f"log {n} " + "x" * 20_000, tool_call_id=f"c{n}")]
    sent = fit(SYSTEM, [], current, 100_000)
    results = [t for t in sent if t.role == "tool"]
    assert all(len(t.content) == len(f"log {n} ") + 20_000 for n, t in enumerate(results) if n >= 8 - KEEP_WHOLE)
    shortened = [t for t in results if "shortened so the request fits" in t.content]
    assert shortened and all(t.content.startswith("log ") and len(t.content) < SHORTENED_CHARS + 100 for t in shortened)
    assert sum(len(t.content) for t in sent) <= 100_000


async def test_a_long_conversation_reaches_the_model_within_its_budget(tmp_path, monkeypatch):
    monkeypatch.setitem(context.BUDGET_CHARS, "local", 30_000)  # the fake model counts as one on this computer
    h = Harness(tmp_path, script=[{"text": "ok " + "w" * 3000}] * 12)
    r = h.submit("first question " + "z" * 3000)
    await h.until(r["task_id"])
    for n in range(10):
        r = h.submit(f"question {n} " + "z" * 3000, conversation_id=r["conversation_id"])
        await h.until(r["task_id"])
    sent = h.requests()[-1]["turns"]
    assert sent[0]["role"] == "system" and "You are Mei" in sent[0]["content"]  # never the part that goes
    assert "left out" in "".join(t["content"] for t in sent) and sent[-1]["content"].startswith("question 9")
