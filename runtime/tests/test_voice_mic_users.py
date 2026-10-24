""""Hey Mei" pauses while another app records (decision 0025).

From `pw-dump --monitor` output recorded in a private PipeWire (pipewire_lab.py, recorded by
`fixtures/record_pw_dump_monitor.py`): another app starts recording, Mei's own recorder, a stream
ending, and pw-dump itself dying. No microphone opens; nothing reads the real graph.
"""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from mei.protocol import VoiceSettings
from mei.voice import mic_users, wire
from mei.voice.controller import PAUSED_NOTE, VoiceController
from mei.voice.mic_users import MicUsers, Recorders, records_mic

RECORDED = Path(__file__).parent / "fixtures" / "pw-dump-monitor.txt"


def batches(text: str) -> list[list]:
    """pw-dump's batches: each a JSON array closed by a line holding only "]"."""
    out, lines = [], []
    for line in text.splitlines():
        lines.append(line)
        if line == "]":
            out.append(json.loads("\n".join(lines)))
            lines = []
    return out


def test_only_other_apps_recording_a_microphone_count():
    assert records_mic({"media.class": "Stream/Input/Audio", "node.name": "Firefox"})
    assert not records_mic({"media.class": "Stream/Input/Audio", "node.name": "mei.microphone"})
    assert not records_mic({"media.class": "Stream/Input/Audio", "node.name": "mei.echo-cancel.1a2b3c4d.capture"})
    assert not records_mic({"media.class": "Stream/Input/Audio", "node.name": "obs", "stream.capture.sink": "true"})
    assert not records_mic({"media.class": "Stream/Input/Audio", "node.name": "x", "stream.monitor": True})
    assert not records_mic({"media.class": "Stream/Input/Audio", "application.id": "org.gnome.VolumeControl"})
    assert not records_mic({"media.class": "Stream/Output/Audio", "node.name": "Firefox"})


def test_the_recorded_graph_says_when_another_app_records():
    """The recording: Mei's recorder comes and goes, then another app's, which then ends."""
    recorders, seen = Recorders(), []
    for batch in batches(RECORDED.read_text()):
        recorders.update(batch)
        seen.append(recorders.others)
    changes = [b for i, b in enumerate(seen) if i == 0 or b != seen[i - 1]]
    assert changes == [False, True, False], seen  # Mei's own never counted


def fake_pw_dump(tmp_path: Path, text: str, then: str = "") -> tuple[str, ...]:
    """A stand-in that prints `text` slowly, like a live graph, then `then` (Python) or exits."""
    data = tmp_path / "out.txt"
    data.write_text(text)
    script = tmp_path / "pw-dump"
    script.write_text(f"#!{sys.executable}\nimport sys, time\n"
                      f"for line in open({str(data)!r}):\n    sys.stdout.write(line); sys.stdout.flush()\n"
                      f"    time.sleep(0.001)\n{then}\n")
    script.chmod(0o755)
    return (str(script),)


async def test_a_watch_follows_the_graph_and_restarts_saying_so(tmp_path, monkeypatch):
    monkeypatch.setattr(mic_users, "RESTARTS", (0.05, 0.05))
    changes, trouble = [], []
    watch = MicUsers(changes.append, trouble.append, fake_pw_dump(tmp_path, RECORDED.read_text()))
    watch.start()
    async with asyncio.timeout(10):
        while not trouble or "trying again" in trouble[-1] or not trouble[-1]:
            await asyncio.sleep(0.02)
    await watch.stop()
    # Each run of pw-dump sees the app start and stop; when it dies, Mei says so and tries again,
    # with back-off, and gives up after a few tries that never worked.
    assert changes[:2] == [True, False]
    assert any("trying again in" in t for t in trouble) and trouble[-1] == (
        "can't tell whether another app is recording (pw-dump stopped)")


async def test_dying_while_another_app_records_lets_the_wake_word_back(tmp_path, monkeypatch):
    """pw-dump dies mid-call: Mei can't tell any more, so it doesn't stay paused on stale news."""
    monkeypatch.setattr(mic_users, "RESTARTS", (30.0,))
    recorded = batches(RECORDED.read_text())
    upto = next(i for i in range(len(recorded)) if any(
        records_mic((o.get("info") or {}).get("props") or {}) for o in recorded[i] if isinstance(o, dict)))
    text = "\n".join(json.dumps(b, indent=2) for b in recorded[:upto + 1]) + "\n"
    changes, trouble = [], []
    watch = MicUsers(changes.append, trouble.append, fake_pw_dump(tmp_path, text))
    watch.start()
    async with asyncio.timeout(10):
        while not trouble or "trying again" not in trouble[-1]:
            await asyncio.sleep(0.02)
    assert changes == [True, False] and "pw-dump stopped" in trouble[-1]
    await watch.stop()


class Stdin:
    def __init__(self) -> None:
        self.sent: list = []

    def write(self, data: bytes) -> None:
        self.sent += [wire.command(line) for line in data.splitlines()]

    def is_closing(self) -> bool:
        return False

    async def drain(self) -> None:
        pass


class Proc:
    def __init__(self) -> None:
        self.stdin = Stdin()


def controller(settings: VoiceSettings) -> tuple[VoiceController, list, Proc]:
    seen: list = []
    v = VoiceController(None, lambda kind, payload: seen.append((kind, payload)), lambda *_: [], Path("/nonexistent"))
    v._settings, v._proc = settings, Proc()
    return v, seen, v._proc


async def test_another_app_recording_pauses_the_wake_word_and_says_so():
    v, seen, proc = controller(VoiceSettings(enabled=True, wake_word=True))
    v._others_recording(True)
    await asyncio.sleep(0)
    assert proc.stdin.sent == [wire.Arm(on=False)] and v.note == PAUSED_NOTE
    v._others_recording(False)
    await asyncio.sleep(0)
    assert proc.stdin.sent[-1] == wire.Arm(on=True) and v.note == ""


@pytest.mark.parametrize(("settings", "locked", "watches"), [
    (VoiceSettings(enabled=True, wake_word=True), False, True),
    (VoiceSettings(enabled=True, wake_word=False), False, False),  # nothing listens: nothing to pause
    (VoiceSettings(enabled=True, wake_word=True, pause_for_apps=False), False, False),
    (VoiceSettings(enabled=True, wake_word=True), True, False)])  # locked: the microphone is closed anyway
async def test_the_graph_is_watched_only_while_the_wake_word_listens(monkeypatch, settings, locked, watches):
    started = []
    monkeypatch.setattr(MicUsers, "start", lambda self: started.append(self))
    v, _seen, _proc = controller(settings)
    v._locked = locked
    await v._follow_mic_users()
    assert bool(started) is watches


async def test_a_reload_while_paused_keeps_the_wake_word_paused():
    v, _seen, proc = controller(VoiceSettings(enabled=True, wake_word=True))
    v._mic_users.others = True
    await v._on_worker(wire.Ready(stt="kroko", tts="piper", device="cpu", wake=True))
    assert proc.stdin.sent == [wire.Arm(on=False)]
