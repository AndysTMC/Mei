"""Spike 0c: PipeWire echo cancellation with the laptop's own speakers and microphone.

Needs the person at the machine, in a quiet room: it plays about 8 s of synthesized speech aloud
and records the microphone meanwhile, twice over (raw, and through the echo canceller), with
nobody speaking. Then, if asked (--barge-in), once more while the person talks over the playback.
Recordings stay in memory; only the numbers are written (results/aec.json). The echo-cancel module
is loaded for the test only and unloaded at the end, even on error.

    ~/.cache/mei-spikes/0c/venv/bin/python aec_test.py [--barge-in]
"""

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from bench import SR, kokoro, vad  # noqa: E402

HERE = Path(__file__).resolve().parent
SOURCE, SINK = "mei_spike_aec_source", "mei_spike_aec_sink"
PLAY = ("Here is what I found. Your next meeting is at three, with Anna and the design team. "
        "It should take about forty minutes, and the slides are already in your Documents folder.")


def pactl(*args: str) -> str:
    return subprocess.run(["/home/linuxbrew/.linuxbrew/bin/pactl", *args], check=True, capture_output=True, text=True).stdout.strip()


def record(target: str, seconds: float, out: dict, key: str) -> None:
    """Record `seconds` of mono 16 kHz audio from a PipeWire node into out[key] (pw-record has no
    duration flag, so read that many bytes and stop it)."""
    proc = subprocess.Popen(["/usr/bin/pw-record", "--raw", "--format", "f32", "--rate", str(SR), "--channels", "1",
                             "--target", target, "-"], stdout=subprocess.PIPE)
    want = int(seconds * SR) * 4
    data = b""
    while len(data) < want:
        chunk = proc.stdout.read(min(65536, want - len(data)))
        if not chunk:
            break
        data += chunk
    proc.terminate()
    proc.wait()
    out[key] = np.frombuffer(data, dtype=np.float32).copy()


def play(samples: np.ndarray, rate: int, sink: str) -> None:
    subprocess.run(["/usr/bin/pw-cat", "--playback", "--raw", "--format", "f32", "--rate", str(rate), "--channels", "1",
                    "--target", sink, "--latency", "20ms", "-"], input=samples.astype(np.float32).tobytes(), check=True)


def rms_db(x: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9))


def speech_fraction(x: np.ndarray) -> float:
    """Share of 32 ms windows Silero calls speech: on an echo-only recording, false barge-in risk."""
    v = vad()
    flagged = total = 0
    for i in range(0, len(x) - 512, 512):
        v.accept_waveform(x[i:i + 512])
        total += 1
        flagged += v.is_speech_detected()
    return round(flagged / max(total, 1), 3)


def run(barge_in: bool) -> dict:
    tts = kokoro(4)
    audio = tts.generate(PLAY, sid=0, speed=1.0)
    speech = np.asarray(audio.samples, dtype=np.float32)
    seconds = len(speech) / audio.sample_rate + 1.0
    mic = pactl("get-default-source")
    module = pactl("load-module", "module-echo-cancel", "aec_method=webrtc", f"source_name={SOURCE}",
                   f"sink_name={SINK}", f"source_master={mic}")
    try:
        time.sleep(1.0)
        got: dict = {}
        threads = [threading.Thread(target=record, args=(mic, seconds, got, "raw")),
                   threading.Thread(target=record, args=(SOURCE, seconds, got, "cancelled"))]
        for t in threads:
            t.start()
        time.sleep(0.3)
        play(speech, audio.sample_rate, SINK)
        for t in threads:
            t.join()
        quiet = {"raw_db": round(rms_db(got["raw"]), 1), "cancelled_db": round(rms_db(got["cancelled"]), 1)}
        quiet["echo_reduction_db"] = round(quiet["raw_db"] - quiet["cancelled_db"], 1)
        quiet["raw_speech_fraction"] = speech_fraction(got["raw"])
        quiet["cancelled_speech_fraction"] = speech_fraction(got["cancelled"])
        result = {"mic": mic, "playback_s": round(seconds - 1.0, 1), "echo_only": quiet}
        if barge_in:
            print("Talk over Mei now, as if interrupting it, until it stops…", flush=True)
            time.sleep(1.0)
            got = {}
            t = threading.Thread(target=record, args=(SOURCE, seconds, got, "cancelled"))
            t.start()
            play(speech, audio.sample_rate, SINK)
            t.join()
            result["talking_over"] = {"cancelled_speech_fraction": speech_fraction(got["cancelled"])}
        return result
    finally:
        pactl("unload-module", module)


if __name__ == "__main__":
    out = run("--barge-in" in sys.argv)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "aec.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
