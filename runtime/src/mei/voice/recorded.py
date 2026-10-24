"""Audio from and to files instead of the microphone and speakers: for tests and for checking a
setup without a person talking. Never used for real conversations, so nothing a person says is
written anywhere (§11.5)."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np

from .parts import CHUNK, SAMPLE_RATE, Speech


class RecordedSource:
    """Plays raw float32 16 kHz mono audio from `path` as if it were the microphone, then silence
    until stopped. `realtime` paces it like a real microphone."""

    def __init__(self, path: Path, realtime: bool = True) -> None:
        self._audio = np.fromfile(path, dtype=np.float32)
        self._realtime = realtime
        self._pos = 0
        self.open = False
        self.opened_at = 0.0  # loop time when the file's first sample "was said"

    async def start(self) -> None:
        if not self.open:
            self.open = True
            self.opened_at = asyncio.get_running_loop().time() - self._pos / SAMPLE_RATE

    async def chunks(self, samples: int = CHUNK) -> AsyncIterator[np.ndarray]:
        loop = asyncio.get_running_loop()
        while self.open:
            chunk = self._audio[self._pos:self._pos + samples]
            self._pos += samples
            if len(chunk) < samples:
                chunk = np.concatenate([chunk, np.zeros(samples - len(chunk), np.float32)])
            # Like a microphone: a chunk exists once its last sample has been said.
            await asyncio.sleep(max(0.0, self.opened_at + self._pos / SAMPLE_RATE - loop.time()) if self._realtime else 0)
            yield chunk

    async def stop(self) -> None:
        self.open = False


class CaptureSink:
    """Appends what would be played to `path` (raw float32 at each speech's rate), at real-time
    pace, so stopping mid-way leaves a shorter file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._stopped = False
        self.played_seconds = 0.0

    async def play(self, speech: Speech) -> None:
        self._stopped = False
        step = speech.rate // 20  # 50 ms
        with open(self._path, "ab") as out:
            for i in range(0, len(speech.samples), step):
                if self._stopped:
                    return
                out.write(np.asarray(speech.samples[i:i + step], dtype=np.float32).tobytes())
                self.played_seconds += min(step, len(speech.samples) - i) / speech.rate
                await asyncio.sleep(step / speech.rate)

    async def drain(self) -> None:
        return None

    async def stop(self) -> None:
        self._stopped = True
