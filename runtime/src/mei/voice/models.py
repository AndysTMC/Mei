"""Where the local voice models live, and which ones there are (decision 0017, spike 0c)."""

import os
from dataclasses import dataclass
from pathlib import Path

from mei.paths import data_dir


RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"


@dataclass(frozen=True)
class Model:
    folder: str  # under the models directory; a file for single-file models
    part: str  # what it is, as people read it
    url: str
    sha256: str  # of the download: pinned, checked before anything is unpacked
    size: int  # bytes to download

    @property
    def archive(self) -> bool:
        return self.url.endswith(".tar.bz2")


def _release(tag: str, name: str, part: str, sha256: str, size: int) -> Model:
    folder = name.removesuffix(".tar.bz2")
    return Model(folder, part, f"{RELEASES}/{tag}/{name}", sha256, size)


# Pinned from k2-fsa's releases (the spike's downloads and the release API agree; the wake-word
# archive has no published digest, so its hash is the spike's).
SILERO = _release("asr-models", "silero_vad.onnx", "voice detection",
                  "9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6", 643_854)
KROKO = _release("asr-models", "sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06.tar.bz2", "speech to text",
                 "c8676e5ff9ac2a85296e53ee0fd4d5fb1db6770e7a7647166eeafe349ade6834", 57_267_600)
PIPER = {"amy": _release("tts-models", "vits-piper-en_US-amy-low.tar.bz2", "voice: Amy",
                         "c70f5284a09a7fd4ed203b39b2ff51cac1432b422b852eb647b481dade3cf639", 67_095_344),
         "lessac": _release("tts-models", "vits-piper-en_US-lessac-medium.tar.bz2", "voice: Lessac",
                            "9e3febfacf0abf4270172d2958bcec246032b7e88efc2720840cc80c93de334e", 67_230_653)}
KOKORO = _release("tts-models", "kokoro-en-v0_19.tar.bz2", "natural voices",
                  "912804855a04745fa77a30be545b3f9a5d15c4d66db00b88cbcd4921df605ac7", 319_625_534)
KWS = _release("kws-models", "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2", "wake word",
               "f170013b4716e41b62b9bfd809687c207cef798ef9bc6534d524e17af9b6561a", 17_626_723)
BASIC = (SILERO, KROKO, PIPER["amy"])  # enough to talk to Mei: ~125 MB
CATALOG = {"silero": SILERO, "kroko": KROKO, "piper-amy": PIPER["amy"], "piper-lessac": PIPER["lessac"],
           "kokoro": KOKORO, "wake": KWS}

# Kokoro v0.19's speakers, by speaker id.
KOKORO_VOICES = ("af", "af_bella", "af_nicole", "af_sarah", "af_sky", "am_adam", "am_michael", "bf_emma",
                 "bf_isabella", "bm_george", "bm_lewis")


def kokoro_label(voice: str) -> str:
    """"bf_emma" → "Emma (British, woman)"; plain "af" is Kokoro's default blend."""
    accent = {"a": "American", "b": "British"}.get(voice[:1], "")
    who = {"f": "woman", "m": "man"}.get(voice[1:2], "")
    name = voice[3:].capitalize() or "Default"
    return f"{name} ({accent}, {who})" if accent and who else name


def models_dir() -> Path:
    """MEI_VOICE_MODELS overrides it (tests and development point it at the spike's models)."""
    override = os.environ.get("MEI_VOICE_MODELS", "")
    return Path(override) if os.path.isabs(override) else data_dir() / "voice" / "models"


def have(model: Model, root: Path | None = None) -> bool:
    return ((root or models_dir()) / model.folder).exists()
