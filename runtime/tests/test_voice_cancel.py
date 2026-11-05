"""Closing voice while the worker still has words on the way (F08): what was heard before Esc is
dropped up to the worker's Cancelled, so it never becomes a request or puts voice back to listening.
The worker is stood in for: commands are recorded, events are fed in the order a pipe would carry them."""

import sys
from pathlib import Path

from mei.store import repo
from mei.voice import wire
from mei.voice.controller import VoiceController

sys.path.insert(0, str(Path(__file__).parent))
from agent_harness import Harness  # noqa: E402


def controller(tmp_path):
    h = Harness(tmp_path, script=[{"text": "A reply."}])
    seen: list[tuple[str, dict]] = []
    v = VoiceController(h.engine, lambda kind, payload: seen.append((kind, payload)), lambda *_: [],
                        tmp_path / "no-models")
    sent: list[str] = []

    async def send(cmd):
        sent.append(type(cmd).__name__)

    async def quiet():
        pass

    v._send, v._follow_mic_users = send, quiet
    return h, v, seen, sent


async def test_words_dictated_before_esc_are_never_sent(tmp_path):
    h, v, seen, sent = controller(tmp_path)
    v.state, v._session, v._dictating = "listening", "dictate", True
    await v.hush()
    assert sent == ["CancelListen"] and v.state == "idle"
    await v._on_worker(wire.Partial(text="never meant to be sent"))
    await v._on_worker(wire.Final(text="never meant to be sent"))
    await v._on_worker(wire.Cancelled())
    assert repo.list_conversations(h.store) == []
    assert not [p for kind, p in seen if kind == "voice.partial"]
    assert v.state == "idle"


async def test_a_listen_on_its_way_when_live_closes_does_not_reopen_it(tmp_path):
    h, v, seen, sent = controller(tmp_path)
    v.state, v._session = "thinking", "button"  # Listen sent; the worker hasn't said Listening yet
    await v.hush()
    assert "CancelListen" in sent
    await v._on_worker(wire.Listening())
    await v._on_worker(wire.Final(text="heard after close"))
    await v._on_worker(wire.Cancelled())
    assert v.state == "idle" and repo.list_conversations(h.store) == []


async def test_after_the_answer_what_is_heard_counts_again(tmp_path):
    h, v, seen, sent = controller(tmp_path)
    v.state, v._session, v._dictating = "listening", "dictate", True
    await v.hush()
    await v._on_worker(wire.Cancelled())
    v._session, v._dictating = "dictate", True  # dictation opened again
    await v._on_worker(wire.Listening())
    await v._on_worker(wire.Final(text="this one is meant"))
    assert v.state == "listening"
    assert [p["text"] for kind, p in seen if kind == "voice.partial"] == ["This one is meant."]
