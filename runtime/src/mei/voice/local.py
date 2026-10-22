"""Local backends on sherpa-onnx (decision 0017): Silero voice detection, Kroko streaming speech to
text, Piper and Kokoro speech, and the keyword spotter for the wake word. They run in the voice
worker, from models read-only at `root`.

Device by measurement: only Kokoro gains from a GPU (spike 0c), so only Kokoro tries one. It falls
back to the CPU on any failure, and says why in `note`.
"""

import asyncio
import logging
import os
from pathlib import Path

import numpy as np
import sherpa_onnx as so

from .models import KOKORO, KROKO, KWS, PIPER, SILERO
from .parts import SAMPLE_RATE, Device, Speech, VoiceError

log = logging.getLogger("mei.voice")
VAD_WINDOW = 512  # Silero's window at 16 kHz
CUDA_PROVIDER = Path(so.__file__).parent / "lib" / "libonnxruntime_providers_cuda.so"
# "Hey Mei" as the keyword spotter's BPE tokens (sounds like "hey may"; spike 0c).
WAKE_TOKENS = "▁HE Y ▁MA Y @HEY_MEI"


def have_kroko(root: Path) -> bool:
    return (root / KROKO.folder).is_dir()


def _need(path: Path, part: str) -> str:
    if not path.exists():
        raise VoiceError(part, f"the model isn't downloaded ({path.name})")
    return str(path)


class SileroVad:
    """Speech or not, per chunk. Silero itself keeps no long hysteresis here (0.1 s); endpointing,
    how much silence ends an utterance, is the pipeline's choice."""

    def __init__(self, root: Path, threshold: float = 0.5) -> None:
        config = so.VadModelConfig()
        config.silero_vad.model = _need(root / SILERO.folder, "voice detection")
        config.silero_vad.threshold = threshold
        config.silero_vad.min_silence_duration = 0.1
        config.silero_vad.min_speech_duration = 0.15
        config.sample_rate = SAMPLE_RATE
        self._config = config
        self._vad = so.VoiceActivityDetector(config, buffer_size_in_seconds=10)
        self._pending = np.zeros(0, np.float32)

    def is_speech(self, chunk: np.ndarray) -> bool:
        self._pending = np.concatenate([self._pending, chunk])
        speech = False
        while len(self._pending) >= VAD_WINDOW:
            self._vad.accept_waveform(self._pending[:VAD_WINDOW])
            self._pending = self._pending[VAD_WINDOW:]
            speech = speech or self._vad.is_speech_detected()
        while not self._vad.empty():  # finished segments: the pipeline doesn't need them back
            self._vad.pop()
        return speech

    def reset(self) -> None:
        self._vad.reset()
        self._pending = np.zeros(0, np.float32)


class KrokoStt:
    """Kroko streaming Zipformer: 12 % WER on synthetic voices, 14 % on the owner's, RTF 0.02 on the
    CPU (spike 0c). Streaming on the CPU: the GPU is slower for 100 ms chunks."""

    name = "kroko"

    def __init__(self, root: Path, threads: int = 2) -> None:
        d = root / KROKO.folder
        self._rec = so.OnlineRecognizer.from_transducer(
            tokens=_need(d / "tokens.txt", "speech to text"), encoder=_need(d / "encoder.onnx", "speech to text"),
            decoder=_need(d / "decoder.onnx", "speech to text"), joiner=_need(d / "joiner.onnx", "speech to text"),
            num_threads=threads, sample_rate=SAMPLE_RATE, feature_dim=80)

    def open(self) -> "KrokoTranscription":
        return KrokoTranscription(self._rec)


class KrokoTranscription:
    def __init__(self, rec: so.OnlineRecognizer) -> None:
        self._rec = rec
        self._stream = rec.create_stream()
        self._text = ""

    async def accept(self, chunk: np.ndarray) -> str | None:
        self._stream.accept_waveform(SAMPLE_RATE, chunk)
        while self._rec.is_ready(self._stream):
            self._rec.decode_stream(self._stream)
        text = self._rec.get_result(self._stream).strip()
        if text == self._text:
            return None
        self._text = text
        return text

    async def finish(self) -> str:
        self._stream.input_finished()
        while self._rec.is_ready(self._stream):
            self._rec.decode_stream(self._stream)
        return self._rec.get_result(self._stream).strip()


class SherpaTts:
    """Piper or Kokoro. Synthesis runs in a thread, so listening for barge-in goes on meanwhile."""

    def __init__(self, name: str, tts: so.OfflineTts, speaker: int, speed: float) -> None:
        self.name = name
        self._tts = tts
        self._speaker = speaker
        self._speed = speed

    async def synthesize(self, text: str) -> Speech:
        audio = await asyncio.to_thread(self._tts.generate, text, sid=self._speaker, speed=self._speed)
        return Speech(np.asarray(audio.samples, dtype=np.float32), audio.sample_rate)


def piper(root: Path, voice: str = "amy", speed: float = 1.0, threads: int = 2) -> SherpaTts:
    model = PIPER.get(voice)
    if model is None:
        raise VoiceError("speech", f"no Piper voice {voice!r}")
    d = root / model.folder
    onnx = next(iter(sorted(d.glob("*.onnx"))), d / "missing.onnx")
    config = so.OfflineTtsModelConfig(vits=so.OfflineTtsVitsModelConfig(
        model=_need(onnx, "speech"), tokens=_need(d / "tokens.txt", "speech"), data_dir=_need(d / "espeak-ng-data", "speech")),
        num_threads=threads)
    return SherpaTts(f"piper-{voice}", so.OfflineTts(so.OfflineTtsConfig(model=config)), 0, speed)


def kokoro(root: Path, speaker: int = 0, speed: float = 1.0, device: Device = "auto",
           threads: int = 4) -> tuple[SherpaTts, str, str]:
    """Kokoro on the GPU when one works, else the CPU. Returns (tts, device used, note)."""
    d = root / KOKORO.folder
    paths = dict(model=_need(d / "model.onnx", "speech"), voices=_need(d / "voices.bin", "speech"),
                 tokens=_need(d / "tokens.txt", "speech"), data_dir=_need(d / "espeak-ng-data", "speech"))
    note = ""
    if device != "cpu":
        usable, why = gpu_usable()
        if usable:
            try:
                tts = _kokoro(paths, threads, "cuda")
                tts.generate("Ready.", sid=speaker, speed=speed)  # a library that loads may still fail to run
                return SherpaTts("kokoro", tts, speaker, speed), "gpu", ""
            except Exception as e:  # noqa: BLE001  any GPU failure means the CPU
                note = f"the GPU didn't work ({str(e)[:120]}), so the CPU is used"
        else:
            note = why if device == "gpu" else ""
        if note:
            log.warning("kokoro: %s", note)
    return SherpaTts("kokoro", _kokoro(paths, threads, "cpu"), speaker, speed), "cpu", note


def _kokoro(paths: dict, threads: int, provider: str) -> so.OfflineTts:
    return so.OfflineTts(so.OfflineTtsConfig(model=so.OfflineTtsModelConfig(
        kokoro=so.OfflineTtsKokoroModelConfig(**paths), num_threads=threads, provider=provider)))


def gpu_usable() -> tuple[bool, str]:
    """Is there an NVIDIA GPU, and an engine build that can use it? (Not whether it will run:
    that is found by trying.)"""
    if not os.path.exists("/dev/nvidiactl"):
        return False, "no NVIDIA GPU here"
    if not CUDA_PROVIDER.exists():
        return False, "the GPU part of the voice engine isn't installed"
    return True, ""


class SherpaWake:
    """sherpa's keyword spotter for "Hey Mei". It misses the latency target (~0.6 s, spike 0c), so
    wake word is off by default; it is a backend behind the same interface as better ones."""

    def __init__(self, root: Path, scratch: Path, threshold: float = 0.25) -> None:
        d = root / KWS.folder
        stem = "epoch-12-avg-2-chunk-16-left-64.int8.onnx"
        keywords = scratch / "mei-keywords.txt"
        keywords.write_text(WAKE_TOKENS + "\n")
        self._kws = so.KeywordSpotter(
            tokens=_need(d / "tokens.txt", "wake word"), encoder=_need(d / f"encoder-{stem}", "wake word"),
            decoder=_need(d / f"decoder-{stem}", "wake word"), joiner=_need(d / f"joiner-{stem}", "wake word"),
            keywords_file=str(keywords), num_threads=1, keywords_threshold=threshold)
        self._stream = self._kws.create_stream()

    def heard(self, chunk: np.ndarray) -> bool:
        self._stream.accept_waveform(SAMPLE_RATE, chunk)
        hit = False
        while self._kws.is_ready(self._stream):
            self._kws.decode_stream(self._stream)
            if self._kws.get_result(self._stream):
                hit = True
                self._kws.reset_stream(self._stream)
        return hit

    def reset(self) -> None:
        self._stream = self._kws.create_stream()
