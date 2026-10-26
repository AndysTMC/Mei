"""The worker's builders: one per engine the worker runs (engines.py is the registry). Each takes the
Load command and the models' folder and returns a backend behind its part's interface (parts.py,
turns.py). The worker calls these and knows no engine by name.
"""

from collections.abc import Callable
from pathlib import Path

from . import local, remote, wire
from .gpu_speaker import GpuKokoro
from .parts import Denoiser, SpeechToText, TextToSpeech
from .turns import TurnDetector, WordTurn

# (the speech, the device it runs on, a note worth saying)
Tts = tuple[TextToSpeech, str, str]


def _kroko(cfg: wire.Load, root: Path, link: remote.CoreLink) -> SpeechToText:
    return local.KrokoStt(root)


def _core_stt(cfg: wire.Load, root: Path, link: remote.CoreLink) -> SpeechToText:
    # Kroko still gives the live partials, and writes the text when the cloud can't.
    return remote.CoreStt(link, local=local.KrokoStt(root) if local.have_kroko(root) else None)


def _piper(cfg: wire.Load, root: Path, link: remote.CoreLink, note_gpu: Callable[[str], None]) -> Tts:
    return local.piper(root, cfg.voice, cfg.speed), "cpu", ""


def _kokoro(cfg: wire.Load, root: Path, link: remote.CoreLink, note_gpu: Callable[[str], None]) -> Tts:
    tts, device, note = local.kokoro(root, cfg.speaker, cfg.speed, "cpu")
    if cfg.gpu_engine and cfg.device != "cpu":  # the GPU when awake, this CPU voice meanwhile
        load = {"models": cfg.models, "speaker": cfg.speaker, "speed": cfg.speed}
        return GpuKokoro(tts, Path(cfg.gpu_engine), load, cfg.gpu_idle_s, note_gpu), "gpu", note
    return tts, device, note


def _core_tts(cfg: wire.Load, root: Path, link: remote.CoreLink, note_gpu: Callable[[str], None]) -> Tts:
    fallback = local.piper(root, cfg.voice, cfg.speed) if local.have_piper(root, cfg.voice) else None  # Piper says what the cloud can't
    return remote.CoreTts(link, fallback), "cloud", ""


STT: dict[str, Callable[[wire.Load, Path, remote.CoreLink], SpeechToText]] = {"kroko": _kroko, "core": _core_stt}
TTS: dict[str, Callable[[wire.Load, Path, remote.CoreLink, Callable[[str], None]], Tts]] = {
    "piper": _piper, "kokoro": _kokoro, "core": _core_tts}
TURN: dict[str, Callable[[wire.Load], TurnDetector]] = {"words": lambda cfg: WordTurn(cfg.end_silence_s)}
# Optional: None when its model isn't downloaded (voice works without it).
DENOISE: dict[str, Callable[[Path], Denoiser | None]] = {
    "gtcrn": lambda root: local.GtcrnDenoiser(root) if local.have_gtcrn(root) else None, "": lambda root: None}


def stt(cfg: wire.Load, root: Path, link: remote.CoreLink) -> SpeechToText:
    return STT[cfg.stt](cfg, root, link)


def tts(cfg: wire.Load, root: Path, link: remote.CoreLink, note_gpu: Callable[[str], None]) -> Tts:
    return TTS[cfg.tts](cfg, root, link, note_gpu)


def denoiser(cfg: wire.Load, root: Path) -> Denoiser | None:
    return DENOISE[cfg.denoise](root)


def turn(cfg: wire.Load) -> TurnDetector:
    return TURN[cfg.turn](cfg)
