"""Voice samples: the same three sentences in every voice, timed on this CPU.

Piper and Kokoro run exactly as Mei runs them (mei.voice.local: sherpa-onnx, Mei's thread counts),
from the models Mei downloads. Each sentence is synthesized on its own, as Mei speaks a reply
sentence by sentence, and the three are joined with a short pause into one WAV per voice.

    runtime/.venv/bin/python spikes/voice-samples/synth.py --models ~/.local/share/mei/voice/models \
        --models <dir with vits-piper-en_US-lessac-medium> --out spikes/voice-samples

Nothing is played. Timings go to results-sherpa.json next to the WAVs.
"""

import argparse
import json
import sys
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "runtime" / "src"))
from mei.voice import local  # noqa: E402
from mei.voice.models import KOKORO, KOKORO_VOICES, PIPER, kokoro_label  # noqa: E402

SENTENCES = (
    "Good morning. It's 7 degrees and cloudy, with rain likely after 3 this afternoon.",
    "I found two emails from Priya about Thursday's review. Do you want me to read the newer one?",
    "Done. I've set a timer for twenty-five minutes, and I'll stay quiet until it ends.",
)
KOKORO_PICKS = ("af", "af_bella", "af_sarah", "am_michael", "bf_emma", "bm_george")
PAUSE_S = 0.6
RUNS = 5  # per sentence; the fastest counts (the least disturbed by other work on the machine)


def find(roots: list[Path], folder: str) -> Path | None:
    return next((r for r in roots if (r / folder).exists()), None)


def size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1e6


def write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())


def sample(tts: local.SherpaTts, out: Path) -> dict:
    tts.synthesize_now("Ready.")  # warm-up, as Mei loads a voice before it speaks
    parts, synth_s, audio_s, rate = [], 0.0, 0.0, 0
    for text in SENTENCES:
        times = []
        for _ in range(RUNS):
            start = time.perf_counter()
            speech = tts.synthesize_now(text)
            times.append(time.perf_counter() - start)
        rate = speech.rate
        parts += [speech.samples, np.zeros(int(PAUSE_S * rate), np.float32)]
        synth_s += min(times)
        audio_s += speech.seconds
    write_wav(out, np.concatenate(parts[:-1]), rate)
    return {"synth_s": round(synth_s, 3), "audio_s": round(audio_s, 2), "rtf": round(synth_s / audio_s, 3),
            "sample_rate": rate, "file": out.name}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", type=Path, action="append", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    roots = [m.expanduser() for m in args.models]
    results = []

    for voice, model in PIPER.items():
        root = find(roots, model.folder)
        if root is None:
            print(f"piper {voice}: not downloaded, skipped")
            continue
        start = time.perf_counter()
        tts = local.piper(root, voice)
        load_s = time.perf_counter() - start
        row = sample(tts, args.out / f"piper-{voice}.wav")
        results.append({"engine": "Piper", "voice": f"{voice} ({model.folder.rsplit('-', 1)[-1]})",
                        "size_mb": round(size_mb(root / model.folder), 1), "load_s": round(load_s, 2), **row})
        print(results[-1])

    root = find(roots, KOKORO.folder)
    if root is not None:
        for name in KOKORO_PICKS:
            start = time.perf_counter()
            tts, device, _ = local.kokoro(root, KOKORO_VOICES.index(name), device="cpu")
            load_s = time.perf_counter() - start
            row = sample(tts, args.out / f"kokoro-{name}.wav")
            results.append({"engine": "Kokoro v0.19", "voice": f"{name}: {kokoro_label(name)}",
                            "size_mb": round(size_mb(root / KOKORO.folder), 1), "load_s": round(load_s, 2),
                            "device": device, **row})
            print(results[-1])

    (args.out / "results-sherpa.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
