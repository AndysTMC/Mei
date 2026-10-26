"""Which engines each part of voice can run on: the engine registry (decision 0029).

One row per engine. Adding one means a row here, its models in models.py, and (for a local engine)
its builder in the worker (build.py); nothing else in Mei names engines. Each has a status:

- **stable**: offered in setup and Settings.
- **experimental**: offered only with "Show experimental engines" on; it may be slow, or wrong.
- **archived**: not offered, but kept and tested, so it can come back if a better one regresses.

This module imports no engine code: the core reads it, and the worker builds from it.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from mei.protocol import VoiceSettings

from .models import GTCRN, KOKORO, KROKO, KWS, PIPER, SILERO, Model

Part = Literal["denoise", "vad", "stt", "tts", "wake", "turn", "cleanup"]
Status = Literal["stable", "experimental", "archived"]
PARTS: tuple[Part, ...] = ("denoise", "vad", "stt", "tts", "wake", "turn", "cleanup")


def _none(_s: VoiceSettings) -> tuple[Model, ...]:
    return ()


@dataclass(frozen=True)
class Engine:
    id: str  # what settings keep (for speech to text on this computer, "local")
    part: Part
    label: str
    status: Status = "stable"
    cloud: bool = False  # runs in the core, with a provider's key; the worker only asks for it
    # Voice works without it until its models are downloaded (it is offered meanwhile).
    optional: bool = False
    # The downloaded models it runs from, for these settings (Piper's depend on the voice).
    needs: Callable[[VoiceSettings], tuple[Model, ...]] = field(default=_none)


def _piper(s: VoiceSettings) -> tuple[Model, ...]:
    return (PIPER.get(s.voice, PIPER["amy"]),)


ENGINES: tuple[Engine, ...] = (
    Engine("gtcrn", "denoise", "GTCRN noise suppression", optional=True, needs=lambda _s: (GTCRN,)),
    Engine("silero", "vad", "Silero", needs=lambda _s: (SILERO,)),
    Engine("local", "stt", "Kroko (on this computer)", needs=lambda _s: (KROKO,)),
    Engine("openai", "stt", "OpenAI", cloud=True),
    Engine("groq", "stt", "Groq", cloud=True),
    Engine("piper", "tts", "Piper", needs=_piper),
    Engine("kokoro", "tts", "Kokoro", needs=lambda _s: (KOKORO,)),
    Engine("openai", "tts", "OpenAI", cloud=True, needs=_piper),  # Piper speaks when the cloud can't
    Engine("gemini", "tts", "Gemini", cloud=True, needs=_piper),
    Engine("kws", "wake", "Keyword spotter", needs=lambda _s: (KWS,)),
    Engine("words", "turn", "By the last word"),
    Engine("rules", "cleanup", "Fillers and stutters"),
)


def engine(part: Part, engine_id: str) -> Engine:
    for e in ENGINES:
        if e.part == part and e.id == engine_id:
            return e
    raise KeyError(f"no {part} engine {engine_id!r}")


def offered(part: Part, experimental: bool = False) -> list[Engine]:
    """The engines a person may choose for `part`: stable ones, and experimental ones if they asked."""
    return [e for e in ENGINES if e.part == part and (e.status == "stable" or experimental and e.status == "experimental")]


def chosen(s: VoiceSettings) -> list[Engine]:
    """The engines these settings run. Kroko always runs: it shows what is heard live, even when a
    cloud provider writes the final text, and writes it when the cloud can't."""
    picks = [engine("denoise", "gtcrn"), engine("vad", "silero"), engine("stt", "local"), engine("tts", s.tts),
             engine("turn", "words"), engine("cleanup", "rules")]
    if s.stt != "local":
        picks.append(engine("stt", s.stt))
    if s.wake_word:
        picks.append(engine("wake", "kws"))
    return picks


def needed(s: VoiceSettings, required_only: bool = False) -> tuple[Model, ...]:
    """The local models these settings use, each once, in the registry's order (`required_only`:
    those voice can't start without)."""
    seen: dict[str, Model] = {}
    for e in chosen(s):
        if required_only and e.optional:
            continue
        for m in e.needs(s):
            seen.setdefault(m.folder, m)
    return tuple(seen.values())


def listing(experimental: bool = False) -> list[dict]:
    """For Settings: each part's engines that may be offered, with their status."""
    return [{"id": e.id, "part": e.part, "label": e.label, "status": e.status, "cloud": e.cloud}
            for part in PARTS for e in offered(part, experimental)]
