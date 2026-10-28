"""Option 3: a second-pass recognizer on the same audio.

    python audio.py tts                    # Kokoro speaks every case's raw words into WAV files (never aloud)
    python audio.py kroko|moonshine-tiny|moonshine-base

There is no recorded dictation to use, so Kokoro (the TTS from spike 0c) reads each case's raw words, fillers
and all, into ~/.cache/mei-spikes/careful-edit/audio. Kroko is what Mei hears with today (streaming, fed in
100 ms chunks the way the runtime does); Moonshine is the second pass, run on the whole utterance once it
has ended, so its whole decode time is latency the person waits for. Writes results/asr-<name>.json.
"""

import json
import resource
import sys
import time
import wave
from pathlib import Path

import numpy as np
import psutil
import sherpa_onnx as so

HERE = Path(__file__).parent
CACHE = Path.home() / ".cache/mei-spikes/careful-edit"
AUDIO = CACHE / "audio"
KOKORO = Path.home() / ".cache/mei-spikes/0c/models/kokoro-int8-en-v0_19"
KROKO = Path.home() / ".cache/mei-spikes/0c/models/sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06"
MOONSHINE = CACHE / "models/sherpa-onnx-moonshine-{}-en-quantized-2026-02-27"
RATE = 16000
THREADS = 4


def mb(n: float) -> float:
    return round(n / 2**20, 1)


def tts(cases: list[dict]) -> None:
    cfg = so.OfflineTtsConfig(model=so.OfflineTtsModelConfig(kokoro=so.OfflineTtsKokoroModelConfig(
        model=str(KOKORO / "model.int8.onnx"), voices=str(KOKORO / "voices.bin"),
        tokens=str(KOKORO / "tokens.txt"), data_dir=str(KOKORO / "espeak-ng-data")), num_threads=THREADS))
    engine = so.OfflineTts(cfg)
    AUDIO.mkdir(parents=True, exist_ok=True)
    for c in cases:
        audio = engine.generate(c["raw"], sid=0, speed=1.0)
        pcm = (np.clip(np.asarray(audio.samples), -1, 1) * 32767).astype(np.int16)
        with wave.open(str(AUDIO / f"{c['id']}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(audio.sample_rate)
            w.writeframes(pcm.tobytes())
        print(c["id"], round(len(pcm) / audio.sample_rate, 2), "s", file=sys.stderr)


def load(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768, w.getframerate()


def to16k(x: np.ndarray, rate: int) -> np.ndarray:
    n = int(len(x) * RATE / rate)
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


class Kroko:
    files = [KROKO / f for f in ("encoder.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt")]

    def __init__(self) -> None:
        self.rec = so.OnlineRecognizer.from_transducer(
            tokens=str(KROKO / "tokens.txt"), encoder=str(KROKO / "encoder.onnx"), decoder=str(KROKO / "decoder.onnx"),
            joiner=str(KROKO / "joiner.onnx"), num_threads=THREADS, sample_rate=RATE, feature_dim=80)

    def run(self, x: np.ndarray) -> tuple[str, float]:
        """Streams the audio in 100 ms chunks; the latency is the compute left once speech has ended
        (decoding the silence after it), not counting the wait for that silence."""
        s = self.rec.create_stream()
        step = RATE // 10
        for i in range(0, len(x), step):
            s.accept_waveform(RATE, x[i:i + step])
            while self.rec.is_ready(s):
                self.rec.decode_stream(s)
        t = time.perf_counter()
        # Kroko holds back the last ~1.5 s: with input_finished() alone 0 of 43 cases came out whole,
        # 37 with 1.2 s of silence after them, all 43 with 1.5 s. 2 s stands in for the pause Mei waits.
        s.accept_waveform(RATE, np.zeros(RATE * 2, np.float32))
        s.input_finished()
        while self.rec.is_ready(s):
            self.rec.decode_stream(s)
        return self.rec.get_result(s).strip(), (time.perf_counter() - t) * 1000


class Moonshine:
    def __init__(self, size: str) -> None:
        d = Path(str(MOONSHINE).format(size))
        self.files = [d / "encoder_model.ort", d / "decoder_model_merged.ort", d / "tokens.txt"]
        self.rec = so.OfflineRecognizer.from_moonshine_v2(
            encoder=str(self.files[0]), decoder=str(self.files[1]), tokens=str(self.files[2]), num_threads=THREADS)

    def run(self, x: np.ndarray) -> tuple[str, float]:
        t = time.perf_counter()
        s = self.rec.create_stream()
        s.accept_waveform(RATE, x)
        self.rec.decode_stream(s)
        return s.result.text.strip(), (time.perf_counter() - t) * 1000


def main() -> None:
    which = sys.argv[1]
    cases = json.loads((HERE / "cases.json").read_text())
    if which == "tts":
        return tts(cases)
    clips = {c["id"]: to16k(*load(AUDIO / f"{c['id']}.wav")) for c in cases}
    proc = psutil.Process()
    base = proc.memory_info().rss
    t0 = time.perf_counter()
    rec = Kroko() if which == "kroko" else Moonshine(which.removeprefix("moonshine-"))
    load_ms = (time.perf_counter() - t0) * 1000
    out = {cid: rec.run(x)[0] for cid, x in clips.items()}  # warm-up pass, and the text
    lat = [rec.run(x)[1] for _ in range(2) for x in clips.values()]
    secs = sum(len(x) for x in clips.values()) / RATE
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    res = {
        "loadavg": [round(x, 1) for x in psutil.getloadavg()],
        "option": which, "input": "audio", "threads": THREADS, "load_ms": round(load_ms),
        "p50_ms": round(float(np.percentile(lat, 50)), 2), "p95_ms": round(float(np.percentile(lat, 95)), 2),
        "max_ms": round(max(lat), 2), "audio_s": round(secs, 1),
        "disk_mb": mb(sum(f.stat().st_size for f in rec.files)), "base_mb": mb(base), "peak_mb": mb(peak),
        "model_ram_mb": mb(peak - base), "out": out,
    }
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / f"results/asr-{which}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    print(f"{which:16} p50 {res['p50_ms']:.1f} ms  p95 {res['p95_ms']:.1f} ms  disk {res['disk_mb']} MB  "
          f"ram +{res['model_ram_mb']} MB", file=sys.stderr)


if __name__ == "__main__":
    main()
