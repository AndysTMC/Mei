"""Stage 5's voice latencies on this machine (§4), from recorded speech: nothing is played aloud and
the microphone is never opened.

Not collected by pytest. Run:  cd runtime && uv run python tests/voice_bench.py [--trials 20]
Models come from MEI_VOICE_MODELS, else the spike's cache. Prints a Markdown report:

- end of speech → final text: endpointing plus the recognizer's last pass, per utterance;
- first sentence synthesized: Piper and Kokoro (on the device Kokoro picks);
- barge-in: speech onset over Mei's answer → playback stopped;
- stopping a real output stream (silence, so inaudible): what PipeWire adds after the stop;
- with `--only gpu`: waking the GPU voice, and its first sentence once awake.

The model's own time to a first sentence is per provider: `MEI_LIVE_CHAT=1 npm run smoke:providers`.
"""

import argparse
import asyncio
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from mei.voice import local, wire
from mei.voice.parts import SAMPLE_RATE, Speech
from mei.voice.pipewire import PipeWireSink
from mei.voice.worker import Worker

UTTERANCES = ("What's the weather like tomorrow?", "Turn on dark mode and open my downloads.",
              "Pause the music, please.", "Remind me to call mum at six.", "How much space is left on my disk?")
ANSWER = ("Here is a long answer about the weather this week. It will be mostly sunny, with a little rain on "
          "Thursday evening, and warm enough to sit outside on the weekend.")
FIRST_SENTENCE = "It will be sunny tomorrow, around eighteen degrees."
ONSET = 0.02  # amplitude where speech starts or ends in synthesized audio


class Timed:
    """The worker's events, with the loop time each was sent."""

    def __init__(self) -> None:
        self.got: list[tuple[float, wire.Event]] = []
        self._changed = asyncio.Event()

    def write(self, data: bytes) -> None:
        now = asyncio.get_running_loop().time()
        for line in data.splitlines():
            self.got.append((now, wire.event(line)))
        self._changed.set()

    def flush(self) -> None:
        pass

    async def until(self, kind, timeout: float = 30.0) -> float:
        async with asyncio.timeout(timeout):
            while True:
                for at, event in self.got:
                    if isinstance(event, kind):
                        return at
                self._changed.clear()
                await self._changed.wait()


async def loaded(models: Path, tmp: Path, mic: np.ndarray, **load) -> tuple[Worker, Timed]:
    events = Timed()
    w = Worker(out=events)
    (tmp / "mic.f32").write_bytes(mic.astype(np.float32).tobytes())
    await w.handle(wire.Load(models=str(models), source_file=str(tmp / "mic.f32"), sink_file=str(tmp / "out.f32"), **load))
    await events.until(wire.Ready, 60)
    return w, events


def speech_bounds(audio: np.ndarray, after_s: float = 0.0) -> tuple[float, float]:
    loud = np.flatnonzero(np.abs(audio[int(after_s * SAMPLE_RATE):]) > ONSET)
    return after_s + loud[0] / SAMPLE_RATE, after_s + loud[-1] / SAMPLE_RATE


async def say(voice, *parts: str | float) -> np.ndarray:
    pieces = [np.zeros(int(p * SAMPLE_RATE), np.float32) if isinstance(p, float) else (await voice.synthesize(p)).samples
              for p in parts]
    return np.concatenate(pieces).astype(np.float32)


async def final_latency(models: Path, tmp: Path, voice, trials: int) -> list[float]:
    out = []
    for i in range(trials):
        mic = await say(voice, 0.4, UTTERANCES[i % len(UTTERANCES)], 3.0)
        _, end = speech_bounds(mic)
        w, events = await loaded(models, tmp, mic)
        await w.handle(wire.Listen())
        at = await events.until(wire.Final)
        out.append(at - (w._source.opened_at + end))
        await w.handle(wire.Quit())
    return out


async def synth_latency(tts, trials: int) -> list[float]:
    await tts.synthesize("Ready.")  # warm
    out = []
    for _ in range(trials):
        t0 = time.monotonic()
        await tts.synthesize(FIRST_SENTENCE)
        out.append(time.monotonic() - t0)
    return out


async def barge_in_latency(models: Path, tmp: Path, voice, trials: int) -> list[float]:
    out = []
    for i in range(trials):
        mic = await say(voice, 1.5, UTTERANCES[i % len(UTTERANCES)], 2.0)  # talks over Mei 1.5 s in
        onset, _ = speech_bounds(mic, after_s=1.4)
        w, events = await loaded(models, tmp, mic, barge_in=True)
        await w.handle(wire.Say(text=ANSWER))
        await w.handle(wire.End())
        at = await events.until(wire.BargeIn)
        out.append(at - (w._source.opened_at + onset))
        await w.handle(wire.Quit())
    return out


async def gpu_latency(models: Path, trials: int) -> tuple[list[float], list[float]]:
    """The GPU voice (decision 0019): waking it (start to ready), then a first sentence once awake."""
    from mei.voice import gpu_engine
    from mei.voice.gpu_speaker import GpuSpeaker
    engine = gpu_engine.engine_dir()
    wake, say = [], []
    for _ in range(trials):
        t0 = time.monotonic()
        speaker = await GpuSpeaker.start(engine, {"models": str(models), "speaker": 0, "speed": 1.0})
        wake.append(time.monotonic() - t0)
        t0 = time.monotonic()
        await speaker.say(FIRST_SENTENCE)
        say.append(time.monotonic() - t0)
        await speaker.stop()
    return wake, say


async def stream_stop(trials: int) -> list[float]:
    """A real output stream playing silence, stopped: how long the stop takes."""
    out = []
    for _ in range(trials):
        sink = PipeWireSink()
        await sink.play(Speech(np.zeros(SAMPLE_RATE * 5, np.float32), SAMPLE_RATE))
        await asyncio.sleep(0.5)
        t0 = time.monotonic()
        await sink.stop()
        out.append(time.monotonic() - t0)
    return out


def row(name: str, values: list[float], target: float | None = None) -> str:
    ms = sorted(v * 1000 for v in values)
    p95 = ms[min(len(ms) - 1, round(0.95 * (len(ms) - 1)))]
    met = "" if target is None else f"{sum(v <= target * 1000 for v in ms)}/{len(ms)} under {target * 1000:.0f} ms"
    return f"| {name} | {len(ms)} | {statistics.median(ms):.0f} | {p95:.0f} | {ms[-1]:.0f} | {met} |"


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--no-stream", action="store_true", help="skip stopping a real (silent) output stream")
    parser.add_argument("--only", choices=("final", "speech", "barge-in", "gpu"), help="just this measure")
    args = parser.parse_args()
    models = Path(os.environ.get("MEI_VOICE_MODELS") or Path.home() / ".cache/mei-spikes/0c/models")
    if not (models / "silero_vad.onnx").exists():
        print(f"no voice models in {models}", file=sys.stderr)
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="mei-voice-bench-"))
    piper = local.piper(models)
    rows, note, barge = [], "", []
    if args.only in (None, "final"):
        rows.append(row("End of speech → final text", await final_latency(models, tmp, piper, args.trials)))
    if args.only in (None, "speech"):
        kokoro, device, note = local.kokoro(models)
        rows.append(row("First sentence, Piper (CPU)", await synth_latency(piper, args.trials)))
        rows.append(row(f"First sentence, Kokoro ({device.upper()})", await synth_latency(kokoro, max(5, args.trials // 4))))
    if args.only == "gpu":  # needs an NVIDIA GPU and the GPU engine (MEI_GPU_ENGINE, or downloaded)
        wake, say = await gpu_latency(models, max(3, args.trials // 4))
        rows.append(row("GPU voice: woken to ready", wake))
        rows.append(row("GPU voice: first sentence once awake", say))
    if args.only in (None, "barge-in"):
        barge = await barge_in_latency(models, tmp, piper, args.trials)
        rows.append(row("Barge-in: onset → playback stopped", barge, 0.35))
    if args.only is None and not args.no_stream:
        rows.append(row("Stopping a real output stream", await stream_stop(5)))
    print("| Measure | Trials | Median ms | p95 ms | Max ms | Target |\n|---|---|---|---|---|---|")
    print("\n".join(rows))
    if barge:
        print("\nBarge-in trials, ms: " + ", ".join(f"{v * 1000:.0f}" for v in barge))
    if note:
        print(f"\nKokoro: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
