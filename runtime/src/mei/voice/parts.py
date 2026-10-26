"""The parts of voice, one interface each (decision 0017): audio in and out, voice activity, wake
word, speech to text, and text to speech. Local backends (local.py, pipewire.py) run in the voice
worker; cloud ones run in the core. Everything else in Mei talks to these interfaces only.

Audio is mono float32 in [-1, 1]. Microphone audio is 16 kHz; speech is at whatever rate the
synthesizer makes, carried alongside it.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np

SAMPLE_RATE = 16_000  # microphone audio everywhere in voice
CHUNK = SAMPLE_RATE // 10  # 100 ms: how microphone audio usually arrives
Device = Literal["auto", "cpu", "gpu"]


class VoiceError(Exception):
    """A part couldn't load or run. `part` names it for the person ("speech to text")."""

    def __init__(self, part: str, message: str) -> None:
        super().__init__(f"{part}: {message}")
        self.part = part
        self.message = message


@dataclass(frozen=True)
class Speech:
    samples: np.ndarray
    rate: int

    @property
    def seconds(self) -> float:
        return len(self.samples) / self.rate


class AudioSource(Protocol):
    """The microphone. Open only between `start` and `stop`: closing it is what turns GNOME's
    microphone indicator off, so nothing listens while Mei isn't."""

    async def start(self) -> None: ...
    def chunks(self, samples: int = CHUNK) -> AsyncIterator[np.ndarray]:
        """Audio as it arrives, in chunks of `samples`, until `stop`."""
        ...
    async def stop(self) -> None: ...


class AudioSink(Protocol):
    """The speakers. `play` queues speech and returns; `drain` waits until it has all been heard;
    `stop` silences it at once (barge-in)."""

    async def play(self, speech: Speech) -> None: ...
    async def drain(self) -> None: ...
    async def stop(self) -> None: ...


class Denoiser(Protocol):
    """Noise out of microphone audio, as it streams. It may hold back a few milliseconds, so what
    comes out of a chunk can be shorter (or empty); `reset` starts a new stream."""

    def process(self, chunk: np.ndarray) -> np.ndarray: ...
    def reset(self) -> None: ...


class Vad(Protocol):
    """Voice activity: is someone speaking in this chunk, and for how long have they been?"""

    def is_speech(self, chunk: np.ndarray) -> bool: ...
    def speaking_for(self) -> float:
        """Seconds the speech going on at the end of the last chunk has lasted (0 in silence),
        counted from when it began, not from when it was detected."""
        ...
    def quiet_for(self) -> float:
        """Seconds of quiet at the end of the last chunk (0 while speaking), counted from when the
        speech ended, not from when that was detected."""
        ...
    def reset(self) -> None: ...


class WakeWord(Protocol):
    def heard(self, chunk: np.ndarray) -> bool: ...
    def reset(self) -> None: ...


class Transcription(Protocol):
    """One utterance being transcribed: fed as it is heard, with partial text along the way."""

    async def accept(self, chunk: np.ndarray) -> str | None:
        """Feed audio; returns the text so far when it changed."""
        ...
    async def finish(self) -> str:
        """No more audio: the final text."""
        ...


class SpeechToText(Protocol):
    name: str

    def open(self) -> Transcription: ...


class TextToSpeech(Protocol):
    name: str

    def warm(self) -> None:
        """The person started talking to Mei: get ready to answer (wake a GPU), without waiting."""
        ...
    async def synthesize(self, text: str) -> Speech: ...


def level_db(chunk: np.ndarray) -> float:
    """RMS level in dBFS (silence is about −60 or lower)."""
    if not len(chunk):
        return -120.0
    return float(20 * np.log10(np.sqrt(np.mean(np.square(chunk, dtype=np.float64))) + 1e-9))
