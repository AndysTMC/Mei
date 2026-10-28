"""KittenTTS samples: the lightweight ONNX models (0.8), the same sentences and timing as synth.py.

KittenTTS isn't a Mei dependency. Run this from a throwaway venv outside the project:

    uv venv -p 3.12 <scratch>/kitten-venv
    VIRTUAL_ENV=<scratch>/kitten-venv uv pip install --no-deps kittenml==0.9.6
    VIRTUAL_ENV=<scratch>/kitten-venv uv pip install onnxruntime espeakng_loader phonemizer soundfile numpy huggingface_hub
    <scratch>/kitten-venv/bin/python -I spikes/voice-samples/kitten.py --cache <scratch>/hf --out spikes/voice-samples

(--no-deps keeps out PyTorch, which only KittenTTS 2 needs.) Four threads, as Mei gives Kokoro.
Nothing is played.
"""

import argparse
import json
import time
import wave
from pathlib import Path

import numpy as np
import onnxruntime as ort

# The same sentences as synth.py (kept apart so this runs without Mei's runtime on the path).
SENTENCES = (
    "Good morning. It's 7 degrees and cloudy, with rain likely after 3 this afternoon.",
    "I found two emails from Priya about Thursday's review. Do you want me to read the newer one?",
    "Done. I've set a timer for twenty-five minutes, and I'll stay quiet until it ends.",
)
PICKS = {
    "KittenML/kitten-tts-mini-0.8": ("Bella", "Jasper", "Luna", "Bruno"),
    "KittenML/kitten-tts-micro-0.8": ("Jasper",),
    "KittenML/kitten-tts-nano-0.8-int8": ("Jasper",),
}
THREADS = 4
PAUSE_S = 0.6
RUNS = 5  # per sentence; the fastest counts, as in synth.py
RATE = 24000

# KittenTTS builds its own ONNX session; give it Mei's thread count rather than every core.
_Session = ort.InferenceSession


def _session(path, sess_options=None, *args, **kwargs):
    options = sess_options or ort.SessionOptions()
    options.intra_op_num_threads = THREADS
    return _Session(path, options, *args, **kwargs)


ort.InferenceSession = _session
from kittenml import KittenTTS  # noqa: E402


def write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())


def size_mb(cache: Path, repo: str) -> float:
    folder = cache / ("models--" + repo.replace("/", "--")) / "blobs"
    return sum(f.stat().st_size for f in folder.rglob("*") if f.is_file()) / 1e6


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    results = []
    for repo, voices in PICKS.items():
        start = time.perf_counter()
        model = KittenTTS(repo, cache_dir=str(args.cache))
        load_s = time.perf_counter() - start  # the first load includes the download
        for voice in voices:
            model.generate("Ready.", voice=voice, clean_text=True)  # warm-up
            parts, synth_s, audio_s = [], 0.0, 0.0
            for text in SENTENCES:
                times = []
                for _ in range(RUNS):
                    start = time.perf_counter()
                    audio = np.asarray(model.generate(text, voice=voice, clean_text=True), np.float32).ravel()
                    times.append(time.perf_counter() - start)
                parts += [audio, np.zeros(int(PAUSE_S * RATE), np.float32)]
                synth_s += min(times)
                audio_s += len(audio) / RATE
            name = repo.split("/")[1].removeprefix("kitten-tts-")
            out = args.out / f"kitten-{name}-{voice.lower()}.wav"
            write_wav(out, np.concatenate(parts[:-1]))
            results.append({"engine": f"KittenTTS {name}", "voice": voice, "size_mb": round(size_mb(args.cache, repo), 1),
                            "load_s": round(load_s, 2), "synth_s": round(synth_s, 3), "audio_s": round(audio_s, 2),
                            "rtf": round(synth_s / audio_s, 3), "sample_rate": RATE, "file": out.name})
            print(results[-1])
    (args.out / "results-kitten.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
