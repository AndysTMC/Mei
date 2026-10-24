"""Echo cancellation in your room (decision 0024): run this at the computer, with its speakers (not
earphones) at your usual volume, in your usual room.

It plays Mei's speech aloud and listens with the microphone, the way voice does with "Interrupt by
talking" on. About three minutes, in three parts:

1. You stay quiet while Mei talks, with echo cancellation: does Mei stop on its own voice, and how
   much of its voice reaches the microphone and is left after the canceller?
2. The same without echo cancellation, for comparison.
3. Mei talks; when the terminal says so, talk over it ("stop, what's the time?"): does it stop, and
   how quickly after your voice started?

Audio stays in memory and is dropped; only numbers are printed (and, in part 3, the words Mei heard,
so you can see it understood you). Not collected by pytest. Run:

    cd runtime && uv run --extra voice python tests/voice_room.py [--replies 5] [--mic NODE] [--output NODE]

Models come from MEI_VOICE_MODELS, else ~/.local/share/mei/voice-models, else the spike's cache.
"""

import argparse
import asyncio
import os
import random
import statistics
import sys
from pathlib import Path

import numpy as np

from mei.voice import wire
from mei.voice.models import models_dir
from mei.voice.parts import CHUNK, level_db
from mei.voice.pipewire import EchoCancelledSource, PipeWireSource, echo_canceller_missing, output_into_ears
from mei.voice.worker import BARGE_GRACE_S, Worker
from voice_bench import ANSWER, Timed

PROMPT = "  >>> Now: talk over Mei."


class Tap:
    """When each chunk the barge-in watch heard through the canceller arrived, and how loud it was."""

    def __init__(self, source: EchoCancelledSource) -> None:
        self.heard: list[tuple[float, float]] = []
        chunks = source.chunks

        async def tapped(samples: int = CHUNK):
            async for chunk in chunks(samples):
                self.heard.append((asyncio.get_running_loop().time(), level_db(chunk)))
                yield chunk
        source.chunks = tapped  # type: ignore[method-assign]


async def reply(w: Worker, events: Timed) -> tuple[bool, float, float]:
    """Mei says one reply; returns whether it stopped on a voice, when it started, and when that was."""
    events.got.clear()
    await w.handle(wire.Say(text=ANSWER))
    await w.handle(wire.End())
    started = await events.until(wire.Speaking, 30)
    ended = await events.until((wire.Spoken, wire.BargeIn), 60)
    barged = any(isinstance(e, wire.BargeIn) for _at, e in events.got)
    if barged:
        await events.until((wire.Final, wire.NoSpeech), 30)
    return barged, started, ended


async def loaded(models: Path, args, echo_cancel: bool) -> tuple[Worker, Timed, Tap | None]:
    events = Timed()
    w = Worker(out=events)
    await w.handle(wire.Load(models=str(models), mic=args.mic, output=args.output, barge_in=True,
                             echo_cancel=echo_cancel))
    await events.until(wire.Ready, 60)  # returns when; the event itself is in events.got
    ready = next(e for _at, e in events.got if isinstance(e, wire.Ready))
    if echo_cancel and not ready.echo_cancel:
        raise SystemExit(f"echo cancellation isn't available here: {ready.note}")
    tap = Tap(w._barge_source) if isinstance(w._barge_source, EchoCancelledSource) else None
    return w, events, tap


async def quiet_part(models: Path, args) -> dict:
    """Parts 1 and 2: you stay quiet; a second recorder hears the plain microphone meanwhile."""
    print("\nParts 1–2: stay quiet while Mei talks.", flush=True)
    raw = PipeWireSource(args.mic)
    levels: list[tuple[float, float]] = []  # (arrival, dBFS) of the plain microphone

    async def record() -> None:
        await raw.start()
        async for chunk in raw.chunks():
            levels.append((asyncio.get_running_loop().time(), level_db(chunk)))

    out = {}
    for echo_cancel in (True, False):
        w, events, tap = await loaded(models, args, echo_cancel)
        recorder = asyncio.ensure_future(record())
        stops, mic, left = 0, [], []
        for _ in range(args.replies):
            barged, started, ended = await reply(w, events)
            stops += barged
            mic += [db for at, db in levels if started + BARGE_GRACE_S <= at <= ended]
            if tap is not None:
                left += [db for at, db in tap.heard if started + BARGE_GRACE_S <= at <= ended]
            await asyncio.sleep(1.0)
        await raw.stop()
        recorder.cancel()
        await w.handle(wire.Quit())
        key = "with" if echo_cancel else "without"
        out[key] = {"stopped_itself": stops, "replies": args.replies, "mic_db": statistics.median(mic) if mic else None}
        if left:
            out[key]["left_db"] = statistics.median(left)
            out[key]["left_p95_db"] = float(np.percentile(left, 95))
        print(f"  {key} echo cancellation: Mei stopped on its own voice {stops} of {args.replies} times", flush=True)
    return out


async def talking_part(models: Path, args, floor_db: float) -> dict:
    """Part 3: you talk over Mei when told to."""
    print("\nPart 3: when the terminal says so, talk over Mei.", flush=True)
    w, events, tap = await loaded(models, args, echo_cancel=True)
    caught, latencies, heard = 0, [], []
    for _ in range(args.replies):
        events.got.clear()
        tap.heard.clear()
        await w.handle(wire.Say(text=ANSWER))
        await w.handle(wire.End())
        await events.until(wire.Speaking, 30)
        await asyncio.sleep(random.uniform(1.5, 4.0))
        print(PROMPT, flush=True)
        prompted = asyncio.get_running_loop().time()
        try:
            barged_at = await events.until(wire.BargeIn, 6)
        except TimeoutError:
            print("  Mei didn't stop.", flush=True)
            await events.until((wire.Spoken, wire.BargeIn), 60)
            continue
        caught += 1
        # Your voice began in the first chunk after the prompt louder than what the canceller leaves.
        onset = next((at - 0.032 for at, db in tap.heard if at > prompted and db > floor_db), None)
        if onset is not None and onset < barged_at:
            latencies.append(barged_at - onset)
        await events.until((wire.Final, wire.NoSpeech), 30)
        heard.append(next((e.text for _at, e in events.got if isinstance(e, wire.Final)), ""))
        print(f"  stopped; heard: {heard[-1]!r}", flush=True)
        await asyncio.sleep(1.0)
    await w.handle(wire.Quit())
    out = {"caught": caught, "replies": args.replies}
    if latencies:
        ms = sorted(1000 * x for x in latencies)
        out |= {"latency_median_ms": round(statistics.median(ms)), "latency_max_ms": round(ms[-1])}
    return out


def report(quiet: dict, talking: dict) -> None:
    w, wo = quiet["with"], quiet["without"]
    print("\n| Measure | Result |\n|---|---|")
    print(f"| Mei's voice at the microphone while it talks (median) | {w['mic_db']:.1f} dBFS |")
    if "left_db" in w:
        print(f"| Left after the canceller (median, p95) | {w['left_db']:.1f}, {w['left_p95_db']:.1f} dBFS |")
        print(f"| Echo removed (median) | {w['mic_db'] - w['left_db']:.1f} dB |")
    print(f"| Mei stopped on its own voice, with echo cancellation | {w['stopped_itself']} of {w['replies']} |")
    print(f"| … without it | {wo['stopped_itself']} of {wo['replies']} |")
    print(f"| Talking over Mei stopped it | {talking['caught']} of {talking['replies']} |")
    if "latency_median_ms" in talking:
        print(f"| Your voice → Mei stopping (estimate*, median, max) | {talking['latency_median_ms']}, "
              f"{talking['latency_max_ms']} ms |")
    print("\n* From the first loud chunk the canceller let through, so it leaves out the microphone's and "
          "speakers' own buffers (~20–40 ms). §4's target is 350 ms.")
    print("Decision 0024: \"Interrupt by talking\" can be on by default with speakers once Mei never stops on "
          "its own voice here and talking over it always works.")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--replies", type=int, default=5, help="replies per part (each ~9 s)")
    parser.add_argument("--mic", default="", help="PipeWire node name; default: the system's")
    parser.add_argument("--output", default="", help="PipeWire node name; default: the system's")
    args = parser.parse_args()
    models = next((p for p in (Path(os.environ.get("MEI_VOICE_MODELS", "")), models_dir(),
                               Path.home() / ".cache/mei-spikes/0c/models") if (p / "silero_vad.onnx").exists()), None)
    if models is None:
        print("no voice models: download them in Mei's Settings → Voice first", file=sys.stderr)
        return 1
    if why := echo_canceller_missing():
        print(f"echo cancellation can't run here: {why}", file=sys.stderr)
        return 1
    if await output_into_ears(args.output):
        print("Sound is going to earphones or a headset: unplug them, so Mei plays through the speakers.", file=sys.stderr)
        return 1
    answer = input("This plays speech through your speakers and listens with your microphone for about three "
                   "minutes. Nothing is recorded to disk. Start? [y/N] ")
    if answer.strip().lower() not in ("y", "yes"):
        return 1
    quiet = await quiet_part(models, args)
    floor = max(-55.0, quiet["with"].get("left_p95_db", -70.0) + 10)
    talking = await talking_part(models, args, floor)
    report(quiet, talking)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
