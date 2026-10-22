"""Spike 0c: sherpa-onnx wake word, VAD, streaming ASR, and TTS on this machine (CPU).

Throwaway measurement code (§22, Stage 0c). It needs no microphone or speakers: test speech is
synthesized with the TTS models themselves (two Piper voices and six of Kokoro's), so ASR word
error rates here are for synthetic speech, not a person's voice. Results go to results/bench.json.

    ./fetch_models.sh
    uv venv --python 3.12 ~/.cache/mei-spikes/0c/venv
    uv pip install --python ~/.cache/mei-spikes/0c/venv/bin/python sherpa-onnx==1.13.8 numpy sounddevice sentencepiece
    ~/.cache/mei-spikes/0c/venv/bin/python bench.py
"""

import json
import os
import re
import resource
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import sherpa_onnx as so

MODELS = Path(os.environ.get("MEI_SPIKE_MODELS", Path.home() / ".cache/mei-spikes/0c/models"))
HERE = Path(__file__).resolve().parent
SR = 16000
RNG = np.random.default_rng(7)

COMMANDS = [
    "what's the weather like tomorrow morning",
    "move last week's invoices into the taxes folder",
    "turn on dark mode and open my downloads",
    "remind me to call the dentist at four thirty",
    "how many unread emails do I have",
    "set the volume to thirty percent",
    "summarize the report I opened yesterday",
    "pause the music",
    "what time is my next meeting",
    "find the photos from the beach trip in august",
    "create a folder called projects twenty twenty six",
    "read me the first paragraph of the readme",
    "is my laptop battery low",
    "switch to the firefox window",
    "copy the total from this invoice",
    "never mind, stop",
    "send the slides to anna when they are ready",
    "make the text on screen a bit bigger",
    "what did we talk about on monday",
    "cancel that",
]
FIRST_SENTENCES = [
    "Sure.",
    "It will be sunny tomorrow, around eighteen degrees.",
    "I moved two invoices into Documents, Invoices, twenty twenty six.",
    "Dark mode is on, and Files is open in Downloads.",
    "You have three unread emails, one of them from Anna.",
    "I couldn't find that file; could you tell me where you saved it?",
]
WAKE = "hey may"  # how "Hey Mei" sounds; spelled so the synthesizer says it that way
NEAR_MISSES = ["they may come later", "hey, maybe tomorrow", "hey man, what's up", "in May we went away",
               "okay, may I ask something", "hey Mike, look at this", "the main thing is", "hey, make it quick"]


# ── Synthesis ───────────────────────────────────────────────────────────────


def kokoro(threads: int, int8: bool = False) -> so.OfflineTts:
    d = MODELS / ("kokoro-int8-en-v0_19" if int8 else "kokoro-en-v0_19")
    return so.OfflineTts(so.OfflineTtsConfig(model=so.OfflineTtsModelConfig(
        kokoro=so.OfflineTtsKokoroModelConfig(model=str(d / ("model.int8.onnx" if int8 else "model.onnx")),
                                              voices=str(d / "voices.bin"),
                                              tokens=str(d / "tokens.txt"), data_dir=str(d / "espeak-ng-data")),
        num_threads=threads)))


def piper(threads: int, voice: str = "amy-low") -> so.OfflineTts:
    d = MODELS / f"vits-piper-en_US-{voice}"
    return so.OfflineTts(so.OfflineTtsConfig(model=so.OfflineTtsModelConfig(
        vits=so.OfflineTtsVitsModelConfig(model=str(d / f"en_US-{voice}.onnx"), tokens=str(d / "tokens.txt"),
                                          data_dir=str(d / "espeak-ng-data")),
        num_threads=threads)))


def to16k(samples: np.ndarray, rate: int) -> np.ndarray:
    if rate == SR:
        return samples.astype(np.float32)
    n = int(len(samples) * SR / rate)
    return np.interp(np.linspace(0, len(samples) - 1, n), np.arange(len(samples)), samples).astype(np.float32)


def say(tts: so.OfflineTts, text: str, sid: int = 0, speed: float = 1.0) -> np.ndarray:
    audio = tts.generate(text, sid=sid, speed=speed)
    return to16k(np.asarray(audio.samples, dtype=np.float32), audio.sample_rate)


def noise(seconds: float, level_db: float) -> np.ndarray:
    return (RNG.standard_normal(int(seconds * SR)) * 10 ** (level_db / 20)).astype(np.float32)


def with_noise(x: np.ndarray, snr_db: float) -> np.ndarray:
    power = float(np.mean(x ** 2)) or 1e-9
    return (x + RNG.standard_normal(len(x)).astype(np.float32) * np.sqrt(power / 10 ** (snr_db / 10))).astype(np.float32)


def speech_end(x: np.ndarray) -> float:
    """Seconds to the last 10 ms frame louder than -40 dBFS."""
    frames = x[: len(x) // 160 * 160].reshape(-1, 160)
    loud = np.nonzero(np.sqrt(np.mean(frames ** 2, axis=1)) > 0.01)[0]
    return (loud[-1] + 1) * 0.01 if len(loud) else 0.0


# ── Measurements ────────────────────────────────────────────────────────────


def bench_tts() -> dict:
    out = {}
    engines = (("kokoro-fp32", lambda t: kokoro(t)), ("kokoro-int8", lambda t: kokoro(t, int8=True)),
               ("piper-amy-low", lambda t: piper(t)), ("piper-lessac-medium", lambda t: piper(t, "lessac-medium")))
    for name, make in engines:
        for threads in (2, 4, 8):
            if name == "kokoro-int8" and threads != 4:
                continue  # slower than real time at any setting here: one row is enough
            tts = make(threads)
            tts.generate("Warm up.", sid=0, speed=1.0)
            firsts, rtfs = [], []
            for text in FIRST_SENTENCES:
                t = time.perf_counter()
                audio = tts.generate(text, sid=0, speed=1.0)
                spent = time.perf_counter() - t
                firsts.append(spent)
                rtfs.append(spent / (len(audio.samples) / audio.sample_rate))
            out[f"{name}/{threads}t"] = {"first_sentence_s_median": round(statistics.median(firsts), 3),
                                         "first_sentence_s_max": round(max(firsts), 3),
                                         "rtf_median": round(statistics.median(rtfs), 3)}
    return out


def recognizer(name: str, threads: int) -> so.OnlineRecognizer:
    if name == "kroko":
        d = MODELS / "sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06"
        files = ("encoder.onnx", "decoder.onnx", "joiner.onnx")
    else:
        d = MODELS / "sherpa-onnx-streaming-zipformer-en-20M-2023-02-17"
        files = ("encoder-epoch-99-avg-1.int8.onnx", "decoder-epoch-99-avg-1.int8.onnx", "joiner-epoch-99-avg-1.int8.onnx")
    return so.OnlineRecognizer.from_transducer(tokens=str(d / "tokens.txt"), encoder=str(d / files[0]),
                                               decoder=str(d / files[1]), joiner=str(d / files[2]),
                                               num_threads=threads, sample_rate=SR, feature_dim=80)


def words(text: str) -> list[str]:
    return re.sub(r"[^a-z' ]", " ", text.lower()).split()


def wer(ref: list[str], hyp: list[str]) -> tuple[int, int]:
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[len(hyp)], len(ref)


def bench_asr(utterances: list[tuple[str, np.ndarray]]) -> dict:
    out = {}
    for name in ("kroko", "zipformer-20M-int8"):
        for threads in (2, 4):
            rec = recognizer(name, threads)
            errors = total = 0
            audio_s = spent = 0.0
            for ref, x in utterances:
                s = rec.create_stream()
                # Trailing silence as the VAD leaves it: it ends an utterance ~0.8 s after the speech
                # (bench_vad). With only 0.3 s the streaming models drop the last word or two.
                padded = np.concatenate([x, np.zeros(int(0.8 * SR), np.float32)])
                t = time.perf_counter()
                for i in range(0, len(padded), 1600):  # 100 ms chunks, as a microphone delivers them
                    s.accept_waveform(SR, padded[i:i + 1600])
                    while rec.is_ready(s):
                        rec.decode_stream(s)
                s.input_finished()
                while rec.is_ready(s):
                    rec.decode_stream(s)
                text = rec.get_result(s)
                spent += time.perf_counter() - t
                audio_s += len(padded) / SR
                e, n = wer(words(ref), words(text))
                errors, total = errors + e, total + n
            out[f"{name}/{threads}t"] = {"rtf": round(spent / audio_s, 3), "wer": round(errors / total, 3)}
    return out


def vad() -> so.VoiceActivityDetector:
    config = so.VadModelConfig()
    config.silero_vad.model = str(MODELS / "silero_vad.onnx")
    config.silero_vad.min_silence_duration = 0.7
    config.silero_vad.min_speech_duration = 0.25
    config.silero_vad.threshold = 0.5
    config.sample_rate = SR
    return so.VoiceActivityDetector(config, buffer_size_in_seconds=30)


def bench_vad(utterances: list[tuple[str, np.ndarray]]) -> dict:
    """Speech end → VAD reports the segment over (endpoint), in audio time and in compute."""
    delays, per_sec = [], []
    for _ref, x in utterances:
        v = vad()
        clip = np.concatenate([noise(0.3, -60), x, noise(2.0, -60)])
        end = 0.3 + speech_end(x)
        found = None
        t = time.perf_counter()
        for i in range(0, len(clip), 512):
            v.accept_waveform(clip[i:i + 512])
            if found is None and not v.empty():
                found = (i + 512) / SR
        per_sec.append((time.perf_counter() - t) / (len(clip) / SR))
        if found is not None:
            delays.append(found - end)
    return {"endpoint_after_speech_end_s_median": round(statistics.median(delays), 3),
            "endpoint_after_speech_end_s_max": round(max(delays), 3), "detected": f"{len(delays)}/{len(utterances)}",
            "cpu_s_per_audio_s": round(statistics.median(per_sec), 4)}


def spotter(threshold: float, score: float) -> so.KeywordSpotter:
    d = MODELS / "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01"
    import sentencepiece as spm  # what so.text2token does for BPE models, without its pinyin import
    pieces = spm.SentencePieceProcessor(model_file=str(d / "bpe.model")).encode(WAKE.upper(), out_type=str)
    keywords = HERE / "results" / "keywords.txt"
    keywords.write_text(f"{' '.join(pieces)} @HEY_MEI\n")
    return so.KeywordSpotter(tokens=str(d / "tokens.txt"), encoder=str(d / "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
                             decoder=str(d / "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
                             joiner=str(d / "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
                             keywords_file=str(keywords), num_threads=1, keywords_threshold=threshold,
                             keywords_score=score)


def spot(kws: so.KeywordSpotter, x: np.ndarray) -> list[float]:
    """Audio times (s) at which the keyword fired, feeding 100 ms chunks."""
    s = kws.create_stream()
    hits = []
    for i in range(0, len(x), 1600):
        s.accept_waveform(SR, x[i:i + 1600])
        while kws.is_ready(s):
            kws.decode_stream(s)
            if kws.get_result(s):
                hits.append((i + 1600) / SR)
                kws.reset_stream(s)
    return hits


def bench_kws(wake_clips: list[np.ndarray], wake_alone: list[np.ndarray], negatives: np.ndarray,
              near: list[np.ndarray]) -> dict:
    out = {}
    for threshold, score in ((0.25, 1.0), (0.35, 1.0), (0.45, 1.0), (0.25, 2.0)):
        kws = spotter(threshold, score)
        found = sum(bool(spot(kws, np.concatenate([noise(0.5, -60), c, noise(1.0, -60)]))) for c in wake_clips)
        delays = []
        for c in wake_alone:
            hits = spot(kws, np.concatenate([noise(0.5, -60), c, noise(1.5, -60)]))
            if hits:
                delays.append(hits[0] - (0.5 + speech_end(c)))
        false = len(spot(kws, negatives))
        near_hits = sum(bool(spot(kws, np.concatenate([noise(0.3, -60), c, noise(0.8, -60)]))) for c in near)
        hours = len(negatives) / SR / 3600
        out[f"threshold {threshold}, score {score}"] = {
            "detected": f"{found}/{len(wake_clips)}",
            "after_keyword_end_s_median": round(statistics.median(delays), 3) if delays else None,
            "false_wakes": false, "speech_hours": round(hours, 3),
            "false_wakes_per_8h_est": round(false / hours * 8, 1),
            "near_misses_fired": f"{near_hits}/{len(near)}"}
    kws = spotter(0.25, 1.0)
    idle = noise(120, -55)
    t, cpu = time.perf_counter(), time.process_time()
    spot(kws, idle)
    out["idle_cpu_core_fraction"] = round((time.process_time() - cpu) / 120, 4)
    out["idle_wall_s_per_audio_s"] = round((time.perf_counter() - t) / 120, 4)
    return out


def corpus(limit_words: int) -> list[str]:
    """Plain English sentences from Mei's own docs: ordinary prose, with plenty of "may"."""
    text = (HERE / "../../docs/architecture/mei-agent-architecture.md").read_text()
    text = re.sub(r"```.*?```|`[^`]*`|\|[^\n]*|#+ [^\n]*|\[[^\]]*\]\([^)]*\)|[*_>]", " ", text, flags=re.S)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if 6 <= len(s.split()) <= 30
                 and re.fullmatch(r"[A-Za-z0-9 ,;:'()\-–—.?!\"]+", s.strip())]
    out, count = [], 0
    for s in sentences:
        out.append(s)
        count += len(s.split())
        if count >= limit_words:
            break
    return out


def main() -> None:
    (HERE / "results").mkdir(exist_ok=True)
    saved = HERE / "results" / "bench.json"
    results: dict = json.loads(saved.read_text()) if "--keep-tts" in sys.argv and saved.exists() else {}
    results["machine"] = {"cpu": os.cpu_count(), "sherpa_onnx": so.__version__}
    t0 = time.perf_counter()
    if "tts" not in results:
        results["tts"] = bench_tts()
        print("tts", json.dumps(results["tts"]), flush=True)

    k = kokoro(4)
    speakers = [(piper(4), 0), (piper(4, "lessac-medium"), 0)] + [(k, sid) for sid in (0, 2, 4, 6, 8, 10)]
    fast = speakers[:2]  # Piper: for the long false-wake corpus
    n = len(speakers)
    asr_set = [(c, with_noise(say(t, c, sid, 1.0), 25) if j % 2 else say(t, c, sid, 1.0))
               for j, c in enumerate(COMMANDS) for t, sid in (speakers[j % n], speakers[(j + 3) % n])]
    results["asr"] = bench_asr(asr_set)
    print("asr", json.dumps(results["asr"]), flush=True)
    results["vad"] = bench_vad(asr_set)
    print("vad", json.dumps(results["vad"]), flush=True)

    wake_clips, wake_alone = [], []
    for t, sid in speakers:
        for speed in (0.9, 1.0, 1.15):
            wake_alone.append(say(t, f"{WAKE.capitalize()}.", sid, speed))
            for k, c in enumerate(COMMANDS[:4]):
                clip = say(t, f"{WAKE.capitalize()}, {c}.", sid, speed)
                wake_clips.append(with_noise(clip, 20) if k % 2 else clip)
    near = [say(t, phrase, sid) for phrase in NEAR_MISSES for t, sid in speakers]
    negatives = np.concatenate([np.concatenate([say(t, s, sid), noise(0.4, -60)])
                                for j, s in enumerate(corpus(4500)) for t, sid in [fast[j % 2]]])
    results["kws"] = bench_kws(wake_clips, wake_alone, negatives, near)
    print("kws", json.dumps(results["kws"]), flush=True)
    results["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    results["minutes"] = round((time.perf_counter() - t0) / 60, 1)
    (HERE / "results" / "bench.json").write_text(json.dumps(results, indent=1) + "\n")
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    sys.exit(main())
