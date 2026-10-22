"""Where the local voice models live, and which ones there are (decision 0017, spike 0c)."""

import os
from dataclasses import dataclass
from pathlib import Path

from mei.paths import data_dir


@dataclass(frozen=True)
class Model:
    folder: str  # under the models directory; a file for single-file models
    part: str  # what it is, as people read it


SILERO = Model("silero_vad.onnx", "voice detection")
KROKO = Model("sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06", "speech to text")
PIPER = {"amy": Model("vits-piper-en_US-amy-low", "voice: Amy"),
         "lessac": Model("vits-piper-en_US-lessac-medium", "voice: Lessac")}
KOKORO = Model("kokoro-en-v0_19", "natural voices")
KWS = Model("sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01", "wake word")

# Kokoro v0.19's speakers, by speaker id.
KOKORO_VOICES = ("af", "af_bella", "af_nicole", "af_sarah", "af_sky", "am_adam", "am_michael", "bf_emma",
                 "bf_isabella", "bm_george", "bm_lewis")


def models_dir() -> Path:
    """MEI_VOICE_MODELS overrides it (tests and development point it at the spike's models)."""
    override = os.environ.get("MEI_VOICE_MODELS", "")
    return Path(override) if os.path.isabs(override) else data_dir() / "voice" / "models"


def have(model: Model, root: Path | None = None) -> bool:
    return ((root or models_dir()) / model.folder).exists()
