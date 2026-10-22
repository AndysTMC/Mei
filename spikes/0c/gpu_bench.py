"""Spike 0c: the same TTS and ASR on the GPU (sherpa-onnx's CUDA 12 / cuDNN 9 build), to compare
with bench.py's CPU numbers. Run with the GPU venv and cuDNN on the library path:

    G=~/.cache/mei-spikes/0c/venv-gpu; SP=$G/lib/python3.12/site-packages/nvidia
    LD_LIBRARY_PATH=$SP/cudnn/lib:$SP/cublas/lib $G/bin/python gpu_bench.py
"""

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import sherpa_onnx as so

sys.path.insert(0, str(Path(__file__).parent))
from bench import COMMANDS, FIRST_SENTENCES, MODELS, SR, say, to16k, wer, words  # noqa: E402

HERE = Path(__file__).resolve().parent


def vram_mb() -> int:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                         capture_output=True, text=True).stdout
    return int(out.split()[0])


def tts(kind: str, provider: str) -> so.OfflineTts:
    if kind == "kokoro":
        d = MODELS / "kokoro-en-v0_19"
        model = so.OfflineTtsModelConfig(kokoro=so.OfflineTtsKokoroModelConfig(
            model=str(d / "model.onnx"), voices=str(d / "voices.bin"), tokens=str(d / "tokens.txt"),
            data_dir=str(d / "espeak-ng-data")), num_threads=4, provider=provider)
    else:
        d = MODELS / "vits-piper-en_US-amy-low"
        model = so.OfflineTtsModelConfig(vits=so.OfflineTtsVitsModelConfig(
            model=str(d / "en_US-amy-low.onnx"), tokens=str(d / "tokens.txt"), data_dir=str(d / "espeak-ng-data")),
            num_threads=4, provider=provider)
    return so.OfflineTts(so.OfflineTtsConfig(model=model))


def bench_tts(kind: str) -> dict:
    before = vram_mb()
    t = time.perf_counter()
    engine = tts(kind, "cuda")
    load = time.perf_counter() - t
    engine.generate("Warm up.", sid=0)
    firsts, rtfs = [], []
    for text in FIRST_SENTENCES:
        t = time.perf_counter()
        audio = engine.generate(text, sid=0)
        spent = time.perf_counter() - t
        firsts.append(spent)
        rtfs.append(spent / (len(audio.samples) / audio.sample_rate))
    return {"load_s": round(load, 2), "first_sentence_s_median": round(statistics.median(firsts), 3),
            "first_sentence_s_max": round(max(firsts), 3), "rtf_median": round(statistics.median(rtfs), 3),
            "vram_mb": vram_mb() - before}


def bench_asr() -> dict:
    d = MODELS / "sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06"
    before = vram_mb()
    rec = so.OnlineRecognizer.from_transducer(tokens=str(d / "tokens.txt"), encoder=str(d / "encoder.onnx"),
                                              decoder=str(d / "decoder.onnx"), joiner=str(d / "joiner.onnx"),
                                              num_threads=2, sample_rate=SR, feature_dim=80, provider="cuda")
    voice = tts("piper", "cpu")
    errors = total = 0
    audio_s = spent = 0.0
    for c in COMMANDS:
        x = np.concatenate([say(voice, c), np.zeros(int(0.8 * SR), np.float32)])
        s = rec.create_stream()
        t = time.perf_counter()
        for i in range(0, len(x), 1600):
            s.accept_waveform(SR, x[i:i + 1600])
            while rec.is_ready(s):
                rec.decode_stream(s)
        s.input_finished()
        while rec.is_ready(s):
            rec.decode_stream(s)
        spent += time.perf_counter() - t
        audio_s += len(x) / SR
        e, n = wer(words(c), words(rec.get_result(s)))
        errors, total = errors + e, total + n
    return {"rtf": round(spent / audio_s, 3), "wer_piper_voice": round(errors / total, 3), "vram_mb": vram_mb() - before}


if __name__ == "__main__":
    out = {"kokoro-fp32/cuda": bench_tts("kokoro"), "piper-amy-low/cuda": bench_tts("piper"), "kroko/cuda": bench_asr()}
    (HERE / "results" / "gpu.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
