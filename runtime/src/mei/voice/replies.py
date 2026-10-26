"""Answering out loud (§11.2, §11.6): which task's reply is spoken, sentence by sentence as it streams,
and the approvals Mei reads back and waits on a spoken "yes, do it" for. It hears the engine's events
from the voice controller and speaks through `say` and `end`; it never touches the microphone.

What is said to Mei, and how it is matched ("stop", "yes, do it"), is phrases.py.
"""

import json
from collections.abc import Callable

from mei.protocol import Envelope

from .phrases import speakable_title, spoken_ok
from .speakable import Sentences


class Replies:
    def __init__(self, engine, say: Callable[[list[str]], None], end: Callable[[], None]) -> None:
        """`say(sentences)` queues them to be spoken; `end()` marks the reply (so far) complete."""
        self._engine = engine
        self._say = say
        self._end = end
        self.task: str | None = None  # the request being answered out loud
        self.asking: str | None = None  # an approval Mei read out and waits on a spoken answer for
        self._message: str | None = None  # its assistant message streaming now
        self._fed = 0  # characters of that message given to `_sentences`
        self._sentences = Sentences()

    def follow(self, task_id: str | None) -> None:
        """Speak this task's reply (None: speak nothing more)."""
        self.task = task_id
        self._message, self._fed, self._sentences = None, 0, Sentences()

    def publish(self, event: Envelope) -> None:
        if self.task is None or event.task_id != self.task:
            return
        p = event.payload
        if event.type == "message.completed" and p["message"]["role"] == "assistant":
            content = p["message"]["content"]
            if p["message"]["id"] != self._message:  # streamed without deltas reaching us
                self._message, self._fed = p["message"]["id"], 0
            self._say(self._sentences.feed(content[self._fed:] + "\n"))
            self._fed = len(content)
        elif event.type == "approval.requested":
            self._ask_aloud(p["approval"])
        elif event.type == "approval.resolved" and p.get("approval_id") == self.asking:
            self.asking = None
        elif event.type == "input.requested":
            self._say([p["request"]["spec"]["question"]])
        elif event.type == "task.finished":
            sentences = self._sentences.flush()
            if p.get("state") == "FAILED":
                sentences.append("Sorry, I couldn't do that.")
            self._say(sentences)
            self.task = None
            self._end()

    def delta(self, event: Envelope) -> None:
        """A piece of the reply streaming (ephemeral): say each sentence as it completes."""
        if self.task is None or event.task_id != self.task or event.type != "message.delta":
            return
        p = event.payload
        if p.get("message_id") != self._message:
            self._message, self._fed = p.get("message_id"), 0
        text = p.get("text") or ""
        self._fed += len(text)
        self._say(self._sentences.feed(text))

    def _ask_aloud(self, approval: dict) -> None:
        """Read the action back and listen for "yes, do it", if a voice may approve it (§11.6):
        local, undo recorded, private, nothing sent off this computer, no data lost. Otherwise the
        card on screen is the only way."""
        action = self._engine.store.read_one("SELECT effects FROM actions WHERE id = ?", (approval["action_id"],))
        effects = json.loads(action["effects"] or "{}") if action is not None else {}
        if spoken_ok(effects):
            self.asking = approval["id"]
            ask = [f"I'd like to {speakable_title(approval['card']['title'])}.", "Say yes, do it, or no."]
        else:
            ask = ["I need your OK for that. It's on screen."]
        self._say(self._sentences.flush() + ask)
        self._end()  # this much is said; the task waits

