"""Voice (Stage 5, decision 0017): the worker's listening, speaking, barge-in, and wake word, run on
the real local models with recorded audio standing in for the microphone and speakers, and its
jail. Skipped where the models aren't downloaded (MEI_VOICE_MODELS, or the spike's cache)."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sherpa = pytest.importorskip("sherpa_onnx")

from mei.voice import jail, local, wire  # noqa: E402
from mei.voice.models import KROKO, KWS, PIPER, SILERO, have  # noqa: E402
from mei.voice.worker import Worker  # noqa: E402

SPIKE_MODELS = Path.home() / ".cache/mei-spikes/0c/models"


@pytest.fixture(scope="module")
def models() -> Path:
    root = Path(os.environ.get("MEI_VOICE_MODELS") or SPIKE_MODELS)
    if not all(have(m, root) for m in (SILERO, KROKO, PIPER["amy"])):
        pytest.skip("voice models not downloaded")
    return root


@pytest.fixture(scope="module")
def voice(models):
    return local.piper(models, "amy")  # 16 kHz, like the microphone


async def say(voice, *parts: str | float) -> np.ndarray:
    """Speech and silences (seconds) in order, as microphone audio."""
    pieces = [np.zeros(int(p * 16000), np.float32) if isinstance(p, float) else (await voice.synthesize(p)).samples
              for p in parts]
    return np.concatenate(pieces).astype(np.float32)


class Events:
    def __init__(self) -> None:
        self.got: list[wire.Event] = []
        self._changed = asyncio.Event()

    def write(self, data: bytes) -> None:
        for line in data.splitlines():
            self.got.append(wire.event(line))
        self._changed.set()

    def flush(self) -> None:
        pass

    def kinds(self) -> list[str]:
        return [type(e).__name__ for e in self.got]

    async def until(self, kind, timeout: float = 20.0) -> wire.Event:
        async with asyncio.timeout(timeout):
            while True:
                for e in self.got:
                    if isinstance(e, kind):
                        return e
                self._changed.clear()
                await self._changed.wait()


async def worker(tmp_path, models, audio: np.ndarray | None = None, **load) -> tuple[Worker, Events, Path]:
    events = Events()
    w = Worker(out=events)
    mic, played = tmp_path / "mic.f32", tmp_path / "played.f32"
    (audio if audio is not None else np.zeros(16000, np.float32)).tofile(mic)
    await w.handle(wire.Load(models=str(models), source_file=str(mic), sink_file=str(played), **load))
    ready = await events.until(wire.Ready)
    assert isinstance(ready, wire.Ready), events.got
    return w, events, played


async def test_listening_streams_partials_and_hears_the_whole_command(tmp_path, models, voice):
    w, events, _ = await worker(tmp_path, models, await say(voice, 0.4, "Turn on dark mode and open my downloads.", 2.0),
                                source_realtime=False)
    await w.handle(wire.Listen())
    final = await events.until(wire.Final)
    assert final.text.lower() == "turn on dark mode and open my downloads"
    partials = [e.text for e in events.got if isinstance(e, wire.Partial)]
    assert len(partials) >= 2 and partials[0] != partials[-1]
    assert events.kinds()[:2] == ["Ready", "Listening"] and "SpeechStarted" in events.kinds()
    assert not w._source.open  # the microphone closes as soon as the utterance is done


async def test_silence_is_no_speech_and_pressing_again_ends_the_utterance(tmp_path, models, voice):
    w, events, _ = await worker(tmp_path, models, np.zeros(16000 * 10, np.float32), source_realtime=False)
    await w.handle(wire.Listen())
    await events.until(wire.NoSpeech)
    # The press comes in a 1 s gap that is too short to end the utterance by itself (1.5 s here).
    w, events, _ = await worker(tmp_path, models, await say(voice, 0.3, "Pause the music.", 1.0, "And then tell me the weather."),
                                end_silence_s=1.5)
    await w.handle(wire.Listen())
    await events.until(wire.Partial)
    async with asyncio.timeout(20):
        while "music" not in next(e.text for e in reversed(events.got) if isinstance(e, wire.Partial)).lower():
            await asyncio.sleep(0.05)
    await w.handle(wire.DoneTalking())  # pressed the shortcut again: done talking
    final = await events.until(wire.Final)
    assert "music" in final.text.lower() and "tell me" not in final.text.lower()


async def test_speaking_plays_each_sentence_then_says_it_is_done(tmp_path, models):
    w, events, played = await worker(tmp_path, models)
    await w.handle(wire.Say(text="Dark mode is on."))
    await w.handle(wire.Say(text="Files is open in Downloads."))
    await w.handle(wire.End())
    await events.until(wire.Spoken, timeout=30)
    assert events.kinds()[1:] == ["Speaking", "Spoken"]
    assert 2.0 < len(np.fromfile(played, dtype=np.float32)) / 16000 < 6.0


async def test_stop_silences_speech_at_once(tmp_path, models):
    w, events, played = await worker(tmp_path, models)
    for sentence in ("Here is a long answer that goes on for a while.", "It has several sentences.",
                     "Nobody wants to hear all of them."):
        await w.handle(wire.Say(text=sentence))
    await w.handle(wire.End())
    await events.until(wire.Speaking)
    await asyncio.sleep(0.5)
    await w.handle(wire.StopSpeaking())
    stopped = await events.until(wire.Spoken)
    assert stopped.stopped and len(np.fromfile(played, dtype=np.float32)) / 16000 < 1.5


async def test_talking_over_mei_stops_it_and_what_was_said_is_heard(tmp_path, models, voice):
    mic = await say(voice, 1.5, "Pause the music please.", 2.0)  # the person starts 1.5 s into Mei's answer
    w, events, played = await worker(tmp_path, models, mic, barge_in=True)
    await w.handle(wire.Say(text="Here is a long answer about the weather this week, which will be mostly sunny."))
    await w.handle(wire.End())
    await events.until(wire.BargeIn, timeout=30)
    final = await events.until(wire.Final, timeout=30)
    assert "the music" in final.text.lower()  # Kroko sometimes hears Piper's "pause" as "cause"
    kinds = events.kinds()
    assert kinds.index("Speaking") < kinds.index("BargeIn") < kinds.index("Listening")
    assert len(np.fromfile(played, dtype=np.float32)) / 16000 < 3.0  # cut off, not played to the end


async def test_the_wake_word_starts_listening(tmp_path, models, voice):
    if not have(KWS, models):
        pytest.skip("wake-word model not downloaded")
    for _attempt in range(8):  # Piper varies a little each time; the spotter hears ~92 % (spike 0c)
        audio = await say(voice, 0.5, "Hey May, pause the music.", 2.0)
        spotter = local.SherpaWake(models, tmp_path)
        if any(spotter.heard(audio[i:i + 1600]) for i in range(0, len(audio), 1600)):
            break
    w, events, _ = await worker(tmp_path, models, audio, wake=True, source_realtime=False)
    await events.until(wire.Woke)
    final = await events.until(wire.Final)
    assert "the music" in final.text.lower()  # as above: "pause" can come out as "cause"


async def test_suspending_closes_the_microphone(tmp_path, models, voice):
    w, events, _ = await worker(tmp_path, models, await say(voice, 0.3, "What time is my next meeting?", 3.0))
    await w.handle(wire.Listen())
    await events.until(wire.SpeechStarted)
    await w.handle(wire.Suspend())
    await events.until(wire.Suspended)
    assert not w._source.open and not any(isinstance(e, wire.Final) for e in events.got)
    await w.handle(wire.Listen())  # nothing listens while suspended
    await asyncio.sleep(0.3)
    assert not w._source.open


async def test_suspending_ends_the_real_capture_stream(tmp_path, models, monkeypatch):
    """With PipeWire's own recorder (a stand-in that streams silence): suspending ends the process,
    so no capture stream is left for `pw-dump` to show, and listening while suspended starts none."""
    from mei.voice import pipewire
    fake = tmp_path / "pw-record"
    fake.write_text(f"#!{sys.executable}\nimport sys, time\n"  # one process, like pw-record
                    "while True:\n    sys.stdout.buffer.write(bytes(6400)); sys.stdout.flush(); time.sleep(0.1)\n")
    fake.chmod(0o755)
    monkeypatch.setattr(pipewire, "PW_RECORD", str(fake))
    events = Events()
    w = Worker(out=events)
    await w.handle(wire.Load(models=str(models)))
    await events.until(wire.Ready)
    try:
        await w.handle(wire.Listen())
        async with asyncio.timeout(10):
            while w._source._proc is None:  # the recorder starts just after "listening" is announced
                await asyncio.sleep(0.02)
        proc = w._source._proc
        assert proc.returncode is None
        await w.handle(wire.Suspend())
        await events.until(wire.Suspended)
        assert proc.returncode is not None and w._source._proc is None
        await w.handle(wire.Listen())
        await asyncio.sleep(0.3)
        assert w._source._proc is None
    finally:
        await w.handle(wire.Quit())


def test_the_jail_has_nowhere_to_keep_audio(tmp_path):
    """Read-only binds, a private tmpfs, and PipeWire's socket: nothing the worker hears can be saved."""
    argv = jail.worker_argv(tmp_path)
    writable = [argv[i + 2] for i, a in enumerate(argv) if a in ("--bind", "--bind-try", "--dev-bind")]
    assert all(path.endswith("/pipewire-0") for path in writable), writable
    assert argv[argv.index("--tmpfs") + 1] == "/tmp" and "--unshare-all" in argv


def test_malformed_commands_are_refused():
    with pytest.raises(Exception):
        wire.command(b'{"op": "say"}')  # no text
    with pytest.raises(Exception):
        wire.command(b'{"op": "format_disk"}')


@pytest.mark.skipif(not jail.available(), reason="needs bubblewrap")
def test_in_its_jail_the_worker_loads_but_reaches_nothing(models):
    proc = subprocess.run(jail.worker_argv(models), input=wire.encode(wire.Diagnose()) + wire.encode(
        wire.Load(models=str(models))) + wire.encode(wire.Quit()), capture_output=True, timeout=120)
    events = [wire.event(line) for line in proc.stdout.splitlines()]
    diagnosis = next(e for e in events if isinstance(e, wire.Diagnosis))
    assert (diagnosis.network, diagnosis.home_visible, diagnosis.session_bus, diagnosis.pulse_socket) == (
        False, False, False, False)
    assert any(isinstance(e, wire.Ready) for e in events) and proc.returncode == 0


# ── Read aloud and the tone, outside any conversation (decision 0030) ────────


def test_every_command_and_event_can_be_decoded():
    """A message type left out of its union is refused by the other side ("Invalid value 'cue'")."""
    import typing
    for base, union in ((wire.Command, wire.AnyCommand), (wire.Event, wire.AnyEvent)):
        kinds = {c for c in vars(wire).values() if isinstance(c, type) and issubclass(c, base) and c is not base}
        assert kinds == set(typing.get_args(union)), kinds ^ set(typing.get_args(union))


async def test_read_aloud_reads_on_its_own_stream_and_is_not_a_conversation(tmp_path, models):
    w, events, played = await worker(tmp_path, models, barge_in=True)
    await w.handle(wire.ReadAloud(id="m1", sentences=["Here is the reply.", "It has two sentences."]))
    assert (await events.until(wire.Reading)).id == "m1"
    done = await events.until(wire.ReadDone)
    assert done.id == "m1" and not done.stopped
    assert not {"Speaking", "Spoken", "Listening", "BargeIn"} & set(events.kinds())  # not Live
    aside = Path(str(played) + ".aside")
    assert aside.exists() and len(np.fromfile(aside, dtype=np.float32)) > 16000 and not played.exists()
    await w.handle(wire.Quit())


async def test_stop_reading_and_live_starting_end_read_aloud(tmp_path, models):
    w, events, _ = await worker(tmp_path, models)
    long = ["This reply goes on for a while, so that there is time to stop it."] * 4
    await w.handle(wire.ReadAloud(id="m1", sentences=long))
    await events.until(wire.Reading)
    await w.handle(wire.StopReading())
    assert (await events.until(wire.ReadDone)).stopped
    events.got.clear()
    await w.handle(wire.ReadAloud(id="m2", sentences=long))
    await events.until(wire.Reading)
    await w.handle(wire.Listen())  # Live starts: reading ends
    done = await events.until(wire.ReadDone)
    assert done.id == "m2" and done.stopped
    await w.handle(wire.Quit())


async def test_the_tone_plays_aside_and_stop_catches_a_reply_still_being_synthesized(tmp_path, models):
    w, events, played = await worker(tmp_path, models)
    await w.handle(wire.Cue())
    await asyncio.sleep(0.6)
    aside = Path(str(played) + ".aside")
    assert aside.exists() and 0 < len(np.fromfile(aside, dtype=np.float32)) and "Speaking" not in events.kinds()
    await w.handle(wire.Say(text="This sentence is stopped before a word of it is heard."))
    await w.handle(wire.End())
    await w.handle(wire.StopSpeaking())  # still synthesizing: nothing is playing yet
    assert (await events.until(wire.Spoken)).stopped
    await asyncio.sleep(1.0)
    assert not played.exists() or len(np.fromfile(played, dtype=np.float32)) == 0
    await w.handle(wire.Quit())


async def test_through_speakers_without_the_canceller_talking_over_mei_stays_off(tmp_path, models, voice, monkeypatch):
    """Decision 0035: Mei would hear its own first words, stop, and take them for the person's."""
    from mei.voice import worker as worker_module

    async def speakers(_output: str = "") -> bool:
        return False
    monkeypatch.setattr(worker_module, "output_into_ears", speakers)
    mic = await say(voice, 1.5, "Pause the music please.", 2.0)
    w, events, played = await worker(tmp_path, models, mic, barge_in=True, echo_cancel=False)
    w._config.sink_file = ""  # as on a real computer, where the speakers are speakers
    await w.handle(wire.Say(text="Here is a long answer about the weather this week, which will be mostly sunny."))
    await w.handle(wire.End())
    failed = await events.until(wire.Failed, timeout=30)
    assert failed.part == "talking over Mei" and "earphones" in failed.message
    await events.until(wire.Spoken, timeout=30)
    assert "BargeIn" not in events.kinds()  # the person spoke 1.5 s in: through speakers it doesn't count
    await w.handle(wire.Quit())
