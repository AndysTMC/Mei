"""Voice (Stage 5, decision 0017): the worker's listening, speaking, barge-in, and wake word, run on
the real local models with recorded audio standing in for the microphone and speakers, and its
jail. Skipped where the models aren't downloaded (MEI_VOICE_MODELS, or the spike's cache)."""

import asyncio
import os
import subprocess
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
    w, events, _ = await worker(tmp_path, models, await say(voice, 0.3, "Pause the music.", 0.15, "And then tell me the weather."))
    await w.handle(wire.Listen())
    await events.until(wire.Partial)
    while "music" not in next(e.text for e in reversed(events.got) if isinstance(e, wire.Partial)).lower():
        await asyncio.sleep(0.05)
    await w.handle(wire.DoneTalking())  # pressed the shortcut again: done talking
    final = await events.until(wire.Final)
    assert "pause the music" in final.text.lower() and "weather" not in final.text.lower()


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
    assert "pause the music" in final.text.lower()
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
    assert "pause the music" in final.text.lower()


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
