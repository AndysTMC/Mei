"""Listening and speaking, built from the parts (parts.py) whatever their backends.

Listening feeds the recognizer everything from the moment it starts (push-to-talk), so nothing is
cut, and ends an utterance after the pause its turn detector asks for (turns.py), then flushes the
recognizer with a tail of silence: without it the last word or two are lost (spike 0c). Speaking synthesizes one sentence
ahead of the one playing, and stops at once on barge-in.
"""

import asyncio
import collections
import contextlib
import math
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import numpy as np

from .parts import (CHUNK, SAMPLE_RATE, AudioSink, AudioSource, Denoiser, Speech, SpeechToText, TextToSpeech, Vad,
                    VoiceError, WakeWord)
from .turns import TurnDetector, WordTurn


@dataclass(frozen=True)
class SpeechStarted:
    pass


@dataclass(frozen=True)
class Partial:
    text: str


@dataclass(frozen=True)
class Final:
    text: str


@dataclass(frozen=True)
class NoSpeech:
    pass


Heard = SpeechStarted | Partial | Final | NoSpeech


@dataclass(frozen=True)
class Endpointing:
    # The pause that ends an utterance, for the word-list turn detector (turns.py). Settings choose it
    # (0.8 s by default, decision 0028). This default is the mechanism's.
    end_silence_s: float = 0.5
    # Silence fed after the end so the recognizer emits the last words: Kroko drops whole words with
    # under ~1 s (and the owner's "ready"/"Monday" in spike 0c). Fed at once: ~40 ms of compute.
    tail_s: float = 1.2
    no_speech_s: float = 30.0  # waiting for someone to start talking; 0: as long as it takes
    max_s: float = 30.0


class WakeGate:
    """Listening for the wake word cheaply: voice detection runs on everything (~0.45 % of a core),
    the keyword spotter (~2.2 %) only while someone is talking. When a voice starts, the spotter
    first hears the second before it was noticed, so the start of "Hey" isn't lost; it keeps going
    for a second after the voice stops."""

    LOOKBACK_CHUNKS = 10  # ~1 s of 100 ms chunks
    HANGOVER_S = 1.0

    def __init__(self, vad: Vad, wake: WakeWord) -> None:
        self._vad = vad
        self._wake = wake
        self._recent: collections.deque = collections.deque(maxlen=self.LOOKBACK_CHUNKS)
        self._spotting = False
        vad.reset()

    def heard(self, chunk: np.ndarray) -> bool:
        voice = self._vad.is_speech(chunk)
        if self._spotting and self._vad.quiet_for() > self.HANGOVER_S:
            self._spotting = False
        if self._spotting:
            return self._wake.heard(chunk)
        self._recent.append(chunk)
        if not voice:
            return False
        self._spotting = True
        self._wake.reset()
        hit = any([self._wake.heard(c) for c in self._recent])  # every chunk in order, even after a hit
        self._recent.clear()
        return hit


class Listener:
    def __init__(self, source: AudioSource, vad: Vad, stt: SpeechToText, endpointing: Endpointing = Endpointing(),
                 turn: TurnDetector | None = None, denoiser: Denoiser | None = None) -> None:
        self._source = source
        self._vad = vad
        self._stt = stt
        self._ep = endpointing
        self._turn = turn or WordTurn(endpointing.end_silence_s)
        self._denoiser = denoiser  # noise out before voice detection and the recognizer hear it
        self._done = asyncio.Event()

    def begin(self) -> None:
        """A new listening starts: forget an earlier "done"."""
        self._done.clear()

    def finish(self) -> None:
        """The person says they're done (pressed again): end the utterance now, and listen no more."""
        self._done.set()

    @property
    def finished(self) -> bool:
        return self._done.is_set()

    async def listen(self, preroll: list[np.ndarray] | None = None, source: AudioSource | None = None,
                     no_speech_s: float | None = None, keep_open: bool = False) -> AsyncIterator[Heard]:
        """One utterance. `preroll`: audio already heard (the start of a barge-in), on `source`
        when it isn't the usual microphone (the echo-cancelled one). `no_speech_s`: how long to
        wait for speech (None: the endpointing's; 0: as long as it takes). The microphone is open
        only while this runs, unless `keep_open` (the next utterance follows on it)."""
        source = source or self._source
        wait = self._ep.no_speech_s if no_speech_s is None else no_speech_s
        self._vad.reset()
        if self._denoiser is not None:
            self._denoiser.reset()
        text = self._stt.open()
        heard = False
        said = ""  # the latest partial: how finished it sounds decides how long the pause must be
        pause: tuple[str, float] | None = None  # (said, quiet that ends the turn): asked once per pause and text
        recent: collections.deque = collections.deque(maxlen=max(1, math.ceil(self._turn.audio_s * SAMPLE_RATE / CHUNK)))
        total = 0.0
        await source.start()
        try:
            chunks = source.chunks()
            for chunk in map(self._clean, preroll or []):
                heard = heard or self._vad.is_speech(chunk)
                if self._turn.audio_s:
                    recent.append(chunk)
                if (partial := await text.accept(chunk)) is not None:
                    yield Partial(partial)
            if heard:
                yield SpeechStarted()
            async for chunk in chunks:
                total += len(chunk) / SAMPLE_RATE
                chunk = self._clean(chunk)
                if self._vad.is_speech(chunk) and not heard:
                    heard = True
                    yield SpeechStarted()
                if (partial := await text.accept(chunk)) is not None:
                    said = partial
                    yield Partial(partial)
                if self._turn.audio_s:
                    recent.append(chunk)
                quiet = self._vad.quiet_for()
                if not quiet:
                    pause = None
                elif heard and (pause is None or pause[0] != said):  # the last words can arrive after the quiet began
                    audio = np.concatenate(recent) if recent else np.zeros(0, np.float32)
                    pause = (said, self._turn.pause_for(said, audio))
                if heard and ((pause is not None and quiet >= pause[1]) or self._done.is_set()):
                    break
                if not heard and ((wait and total >= wait) or self._done.is_set()):
                    yield NoSpeech()
                    return
                if total >= self._ep.max_s:
                    break
        finally:
            if not keep_open:
                await source.stop()
        await text.accept(np.zeros(int(self._ep.tail_s * SAMPLE_RATE), np.float32))
        final = await text.finish()
        yield Final(final) if final else NoSpeech()


    def _clean(self, chunk: np.ndarray) -> np.ndarray:
        return chunk if self._denoiser is None else self._denoiser.process(chunk)


class Speaker:
    """Speaks sentences in order. `say` queues one (text, or audio already made: a tone); `end` marks
    the reply complete. `on_start` is called when the first audio of a reply plays, `on_done` once
    all of it has been heard. `pending` is true from the first `say` until then, so a Stop while the
    first sentence is still being synthesized stops it too."""

    LOOKAHEAD = 2

    def __init__(self, tts: TextToSpeech, sink: AudioSink, on_start: Callable[[], None],
                 on_done: Callable[[], None], on_error: Callable[[VoiceError], None] = lambda _e: None) -> None:
        self._tts = tts
        self._sink = sink
        self._on_start = on_start
        self._on_done = on_done
        self._on_error = on_error
        self._texts: asyncio.Queue[str | Speech | None] = asyncio.Queue()
        self._speech: asyncio.Queue = asyncio.Queue(maxsize=self.LOOKAHEAD)
        self._tasks: list[asyncio.Task] = []
        self._unheard = 0  # sentences said but not yet played
        self.speaking = False
        self.started_at = 0.0

    @property
    def pending(self) -> bool:
        return self.speaking or self._unheard > 0

    def say(self, sentence: str | Speech) -> None:
        self._ensure_running()
        self._unheard += 1
        self._texts.put_nowait(sentence)

    def end(self) -> None:
        """No more sentences in this reply."""
        self._ensure_running()
        self._texts.put_nowait(None)

    async def stop(self) -> None:
        """Silence now, and drop everything queued (barge-in, or the person's Stop)."""
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []
        self._texts = asyncio.Queue()
        self._speech = asyncio.Queue(maxsize=self.LOOKAHEAD)
        await self._sink.stop()
        self._unheard = 0
        self.speaking = False

    def _ensure_running(self) -> None:
        if not self._tasks:
            loop = asyncio.get_running_loop()
            self._tasks = [loop.create_task(self._synthesize()), loop.create_task(self._play())]

    async def _synthesize(self) -> None:
        while True:  # the end marker (None) passes through to the player
            text = await self._texts.get()
            if text is None:
                await self._speech.put(None)
                continue
            try:
                await self._speech.put(text if isinstance(text, Speech) else await self._tts.synthesize(text))
            except VoiceError as e:  # one sentence that can't be said: say the rest
                self._unheard -= 1
                self._on_error(e)

    async def _play(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            speech = await self._speech.get()
            if speech is None:
                await self._sink.drain()
                self.speaking = False
                self._on_done()
                continue
            if not self.speaking:
                self.speaking = True
                self.started_at = loop.time()
                self._on_start()
            await self._sink.play(speech)
            self._unheard -= 1
