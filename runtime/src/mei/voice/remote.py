"""The worker's side of cloud speech (decision 0017): backends that ask the core, which has the
network and the keys, over the worker's pipe. They fit the same interfaces as the local ones, so
listening and speaking don't change.

Speech to text by the core still shows live partials from a local recognizer when one is loaded;
the utterance goes up once the person stops.
"""

import asyncio
import base64
import itertools
from collections.abc import Callable

import numpy as np

from . import wire
from .parts import SAMPLE_RATE, Speech, SpeechToText, VoiceError

TIMEOUT_S = 30.0


class CoreLink:
    """Requests to the core and their answers, by id."""

    def __init__(self, emit: Callable[[wire.Event], None]) -> None:
        self._emit = emit
        self._ids = itertools.count(1)
        self._waiting: dict[str, asyncio.Future] = {}

    async def ask(self, make: Callable[[str], wire.Event]) -> wire.Command:
        request_id = str(next(self._ids))
        future = asyncio.get_running_loop().create_future()
        self._waiting[request_id] = future
        self._emit(make(request_id))
        try:
            return await asyncio.wait_for(future, TIMEOUT_S)
        except TimeoutError:
            raise VoiceError("cloud speech", f"no answer within {TIMEOUT_S:.0f} s") from None
        finally:
            self._waiting.pop(request_id, None)

    def answer(self, reply: wire.Transcript | wire.Audio) -> None:
        future = self._waiting.get(reply.id)
        if future is not None and not future.done():
            future.set_result(reply)


def pcm(samples: np.ndarray) -> str:
    return base64.b64encode(np.asarray(samples, dtype=np.float32).tobytes()).decode()


def samples(data: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(data), dtype=np.float32).copy()


class CoreStt:
    name = "cloud"

    def __init__(self, link: CoreLink, partials: SpeechToText | None) -> None:
        self._link = link
        self._partials = partials

    def open(self) -> "CoreTranscription":
        return CoreTranscription(self._link, self._partials.open() if self._partials else None)


class CoreTranscription:
    def __init__(self, link: CoreLink, local) -> None:
        self._link = link
        self._local = local
        self._audio: list[np.ndarray] = []

    async def accept(self, chunk: np.ndarray) -> str | None:
        self._audio.append(chunk)
        return await self._local.accept(chunk) if self._local is not None else None

    async def finish(self) -> str:
        audio = np.concatenate(self._audio) if self._audio else np.zeros(0, np.float32)
        reply = await self._link.ask(lambda i: wire.Transcribe(id=i, pcm=pcm(audio)))
        if reply.error:
            raise VoiceError("speech to text", reply.error)
        return reply.text.strip()


class CoreTts:
    name = "cloud"

    def __init__(self, link: CoreLink) -> None:
        self._link = link

    async def synthesize(self, text: str) -> Speech:
        reply = await self._link.ask(lambda i: wire.Synthesize(id=i, text=text))
        if reply.error:
            raise VoiceError("speech", reply.error)
        return Speech(samples(reply.pcm), reply.rate or SAMPLE_RATE)
