"""The voice worker (§5.4, decision 0017): microphone, speakers, and the local voice models, in a
jail with no network and no files of the person's (jail.py). It decides nothing about tasks: the
core tells it to listen and what to say, and it reports what it hears.

    python -m mei.voice.worker      (JSON lines: commands on stdin, events on stdout; wire.py)

Only one thing reads the microphone at a time: listening, the barge-in watch while speaking, or
the wake word while armed. Barge-in and wake hand the open microphone straight to listening, with
the audio they already heard, so the first words aren't lost. The barge-in watch hears the
microphone through PipeWire's echo canceller when that is on and available (decision 0024), so
Mei's own voice from the speakers doesn't count as talking over it.
"""

import asyncio
import collections
import contextlib
import logging
import math
import os
import socket
import sys
from pathlib import Path

import msgspec
import numpy as np

from . import build, local, pipeline, remote, wire
from .gpu_speaker import GpuKokoro
from .parts import CHUNK, SAMPLE_RATE, AudioSink, AudioSource, Speech, VoiceError, level_db, loudness
from .pipewire import EchoCancelledSource, PipeWireSink, PipeWireSource, echo_canceller_missing, output_into_ears
from .recorded import CaptureSink, RecordedSource

log = logging.getLogger("mei.voice")
BARGE_GRACE_S = 0.3  # after speech starts, before talking over it counts (the Hermes lesson, §11.4)
BARGE_SPEECH_S = 0.2  # speech this long stops Mei
PREROLL_S = 0.8  # of the barge-in or wake audio, handed to listening
# The barge-in watch reads Silero's own 32 ms windows, so it decides as soon as the speech has
# lasted long enough rather than at the end of a 100 ms chunk: ~50 ms sooner (decision 0024).
BARGE_CHUNK = local.VAD_WINDOW


class Worker:
    def __init__(self, out=None) -> None:
        self._out = out or sys.stdout.buffer
        self._source: AudioSource | None = None
        self._barge_source: AudioSource | None = None  # the barge-in watch's: echo-cancelled, when that runs
        self._sink: AudioSink | None = None
        self._vad: local.SileroVad | None = None
        self._wake: local.SherpaWake | None = None
        self._listener: pipeline.Listener | None = None
        self._speaker: pipeline.Speaker | None = None
        # Speech outside any conversation, on a stream of its own (decision 0030): the tone and
        # check-ins while Mei works, and a reply's Read aloud. No Speaking or Spoken, nothing to
        # talk over, no listening after.
        self._aside: pipeline.Speaker | None = None
        self._reading: str | None = None  # the message Read aloud is reading
        self._said_no_barge = False  # said once per load why talking over Mei is off
        self._tts = None  # what speaks: warmed when listening starts
        self._gpu_note = ""
        self._config: wire.Load | None = None
        self._mic_task: asyncio.Task | None = None  # whatever holds the microphone now
        self._mic_job = ""  # "listen", "wake", or "barge" while _mic_task runs
        self._armed = False
        self._suspended = False
        self._link = remote.CoreLink(self.emit)  # cloud speech, through the core

    def emit(self, event: wire.Event) -> None:
        self._out.write(wire.encode(event))
        self._out.flush()

    # ── Commands ─────────────────────────────────────────────────────────────

    async def handle(self, cmd: wire.Command) -> bool:
        """Act on one command. False: quit."""
        match cmd:
            case wire.Load():
                await self._load(cmd)
            case wire.Listen():
                if self._ready() and not self._suspended:
                    await self._aside_stop()  # Live starting ends Read aloud
                    if await self._speaker_stop():  # talking while Mei speaks: it stops for you
                        self.emit(wire.Spoken(stopped=True))
                    await self._take_mic("listen", self._listen(no_speech_s=cmd.no_speech_s,
                                                                continuous=cmd.continuous))
            case wire.DoneTalking():
                if self._listener is not None:
                    self._listener.finish()
            case wire.CancelListen():
                await self._release_mic()
                self.emit(wire.Cancelled())  # after everything the listening it stopped said
                self._rearm()
            case wire.Say(text=text):
                if self._ready() and not self._suspended and text.strip():
                    if self._reading is not None:
                        await self._aside_stop()  # a spoken answer takes over from Read aloud
                    self._speaker.say(text)
            case wire.End():
                if self._ready() and not self._suspended:
                    self._speaker.end()
            case wire.Cue(text=text):
                if self._ready() and not self._suspended and not self._speaker.pending and self._reading is None:
                    self._aside.say(tone() if not text else text)
                    self._aside.end()
            case wire.ReadAloud(id=read_id, sentences=sentences):
                if self._ready() and not self._suspended:
                    await self._aside_stop()
                    self._reading = read_id
                    for sentence in (s for s in sentences if s.strip()):
                        self._aside.say(sentence)
                    self._aside.end()
            case wire.StopReading():
                await self._aside_stop()
            case wire.StopSpeaking():
                if await self._speaker_stop():
                    self.emit(wire.Spoken(stopped=True))
                self._rearm()
            case wire.Arm(on=on):
                self._armed = on and self._wake is not None
                if self._armed:
                    self._rearm()
                elif self._mic_job == "wake":
                    await self._release_mic()
            case wire.Suspend():
                self._suspended = True
                await self._release_mic()
                await self._speaker_stop()
                await self._aside_stop()
                self.emit(wire.Suspended())
            case wire.Resume():
                self._suspended = False
                self._rearm()
            case wire.Diagnose():
                self.emit(diagnose())
            case wire.Transcript() | wire.Audio():
                self._link.answer(cmd)
            case wire.MeasureMic(seconds=seconds):
                if self._ready() and not self._suspended:
                    await self._take_mic("measure", self._measure(seconds))
            case wire.Quit():
                await self._release_mic()
                await self._speaker_stop()
                await self._aside_stop()
                await self._close_tts()
                return False
        return True

    def _note_gpu(self, message: str) -> None:
        if message != self._gpu_note:  # once per cause, not once per sentence
            self._gpu_note = message
            self.emit(wire.Failed(part="speech", message=message))

    async def _close_tts(self) -> None:
        tts, self._tts = self._tts, None
        if isinstance(tts, GpuKokoro):
            await tts.close()

    def _ready(self) -> bool:
        if self._listener is None or self._speaker is None:
            self.emit(wire.Failed(part="voice", message="not loaded"))
            return False
        return True

    async def _load(self, cfg: wire.Load) -> None:
        root = Path(cfg.models)
        await self._release_mic()  # nothing keeps recording through the sources being replaced
        await self._speaker_stop()  # nor speaking through the speakers being replaced
        await self._aside_stop()
        await self._close_tts()
        try:
            self._vad = local.SileroVad(root)
            stt = build.stt(cfg, root, self._link)
            tts, device, note = build.tts(cfg, root, self._link, self._note_gpu)
            turn = build.turn(cfg)
            denoiser = build.denoiser(cfg, root)
            self._wake = local.SherpaWake(root, Path("/tmp"), cfg.wake_threshold) if cfg.wake else None
        except VoiceError as e:
            self.emit(wire.Failed(part=e.part, message=e.message))
            return
        except Exception as e:  # noqa: BLE001  a model that won't load: say which part, keep running
            self.emit(wire.Failed(part="voice", message=str(e)[:300]))
            return
        self._source = RecordedSource(Path(cfg.source_file), cfg.source_realtime) if cfg.source_file \
            else PipeWireSource(cfg.mic)
        self._barge_source, echo_note = self._source, ""
        if cfg.barge_in and cfg.echo_cancel and not cfg.source_file:
            if missing := echo_canceller_missing():
                echo_note = f"{missing}, so talking over Mei works with earphones only"
            else:
                self._barge_source = EchoCancelledSource(cfg.mic, cfg.output)
        self._sink = CaptureSink(Path(cfg.sink_file)) if cfg.sink_file else PipeWireSink(cfg.output)
        aside_sink = CaptureSink(Path(cfg.sink_file + ".aside")) if cfg.sink_file else PipeWireSink(cfg.output)
        ep = pipeline.Endpointing(end_silence_s=cfg.end_silence_s, no_speech_s=cfg.quiet_s)
        self._listener = pipeline.Listener(
            self._source, self._vad, stt, ep, turn, denoiser,
            on_heard=lambda chunk: self.emit(wire.Loudness(source="mic", levels=loudness(chunk, SAMPLE_RATE))))
        self._speaker = pipeline.Speaker(tts, self._sink, on_start=self._spoke, on_done=self._spoken,
                                         on_error=lambda e: self.emit(wire.Failed(part=e.part, message=e.message)),
                                         on_play=lambda s: self.emit(wire.Loudness(source="mei",
                                                                                   levels=loudness(s.samples, s.rate))))
        self._aside = pipeline.Speaker(tts, aside_sink, on_start=self._aside_started, on_done=self._aside_done,
                                       on_error=lambda e: self.emit(wire.Failed(part=e.part, message=e.message)))
        self._config, self._tts = cfg, tts
        self._said_no_barge = False
        self._armed = cfg.wake and self._wake is not None
        self.emit(wire.Ready(stt=stt.name, tts=tts.name, device=device, note="; ".join(n for n in (note, echo_note) if n),
                             wake=self._wake is not None, echo_cancel=self._barge_source is not self._source,
                             version=wire.VERSION))
        self._rearm()

    # ── The microphone ───────────────────────────────────────────────────────

    async def _take_mic(self, job: str, work) -> None:
        await self._release_mic()
        self._hand_mic(job, work)

    def _hand_mic(self, job: str, work) -> None:
        """Give the (possibly open) microphone to `work` without closing it."""
        self._mic_job = job
        self._mic_task = asyncio.ensure_future(work)
        self._mic_task.add_done_callback(self._mic_done)

    def _mic_done(self, task: asyncio.Task) -> None:
        """A microphone job that crashed says so, rather than vanishing."""
        if task.cancelled() or task.exception() is None:
            return
        log.error("voice: %s failed", task.get_name(), exc_info=task.exception())
        self.emit(wire.Failed(part="voice", message=str(task.exception())[:300]))

    async def _release_mic(self) -> None:
        task, self._mic_task, self._mic_job = self._mic_task, None, ""
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for source in {self._source, self._barge_source} - {None}:
            await source.stop()

    def _rearm(self) -> None:
        """Back to waiting for the wake word, if it is on and nothing else holds the microphone."""
        if self._armed and not self._suspended and self._mic_task is None and self._wake is not None \
                and not (self._speaker and self._speaker.speaking) and not (self._aside and self._aside.pending):
            self._hand_mic("wake", self._wait_for_wake())

    async def _listen(self, preroll: list | None = None, source: AudioSource | None = None,
                      no_speech_s: float | None = None, continuous: bool = False) -> None:
        """One utterance, from `source` if given (the open one barge-in heard it on); or, if
        `continuous`, one after another on the open microphone until the person says they're done
        (dictation: the microphone stays open across pauses, decision 0026)."""
        task = asyncio.current_task()
        source = source or self._source
        self._listener.begin()
        self.emit(wire.Listening())
        if self._tts is not None:
            self._tts.warm()  # wake the GPU while the person talks
        try:
            while True:
                async for heard in self._listener.listen(preroll, source, no_speech_s, keep_open=continuous):
                    match heard:
                        case pipeline.SpeechStarted():
                            self.emit(wire.SpeechStarted())
                        case pipeline.Partial(text=text):
                            self.emit(wire.Partial(text=text))
                        case pipeline.Final(text=text):
                            self.emit(wire.Final(text=text))
                        case pipeline.NoSpeech():
                            self.emit(wire.NoSpeech())
                if not continuous or self._listener.finished:
                    break
                preroll = None
        except VoiceError as e:
            self.emit(wire.Failed(part=e.part, message=e.message, ended=True))
        finally:
            if continuous:
                await source.stop()
            if self._mic_task is task:
                self._mic_task, self._mic_job = None, ""
        self._rearm()

    async def _measure(self, seconds: float) -> None:
        """The microphone's level in silence: an overdriven input (spike 0c: silence at −3 dB, a
        fifth of it clipped) breaks voice detection. Only numbers leave; the audio is dropped."""
        task = asyncio.current_task()
        got, total = [], int(seconds * SAMPLE_RATE)
        try:
            await self._source.start()
            async for chunk in self._source.chunks():
                got.append(chunk)
                if sum(len(c) for c in got) >= total:
                    break
        finally:
            if self._mic_task is task:
                self._mic_task, self._mic_job = None, ""
            await self._source.stop()
        audio = np.concatenate(got) if got else np.zeros(1, np.float32)
        peak = float(np.max(np.abs(audio)))
        self.emit(wire.MicLevel(db=round(level_db(audio), 1), peak_db=round(float(20 * np.log10(peak + 1e-9)), 1),
                                clipped_pct=round(100 * float(np.mean(np.abs(audio) >= 0.99)), 2)))
        self._rearm()

    async def _wait_for_wake(self) -> None:
        heard = await self._watch(pipeline.WakeGate(self._vad, self._wake).heard, self._source)
        if heard is not None:
            self._wake.reset()
            self.emit(wire.Woke())
            self._hand_mic("listen", self._listen(heard))

    async def _watch_barge_in(self) -> None:
        loop = asyncio.get_running_loop()

        def talking_over(chunk) -> bool:
            if loop.time() - self._speaker.started_at < BARGE_GRACE_S:
                self._vad.reset()  # speech (or Mei's echo) in the grace window doesn't count
                return False
            self._vad.is_speech(chunk)
            return self._vad.speaking_for() >= BARGE_SPEECH_S

        self._vad.reset()
        source = self._barge_source
        ears = await output_into_ears(self._config.output)
        if isinstance(source, EchoCancelledSource) and ears:
            source = self._source  # no echo to cancel, and the canceller would only slow barge-in down
        if source is self._source and not ears and not self._config.sink_file:
            # Speakers and the plain microphone: Mei would hear itself and stop at its own first words,
            # then take them for the person's (decision 0035). It needs earphones or the canceller.
            if not self._said_no_barge:
                self._said_no_barge = True
                self.emit(wire.Failed(part="talking over Mei", message="it needs earphones, or Cancel echo from "
                                      "speakers turned on: through speakers Mei would hear itself"))
            return
        try:
            heard = await self._watch(talking_over, source, BARGE_CHUNK)
        except VoiceError as e:
            heard = None
            if isinstance(source, EchoCancelledSource):
                source.failure = e.message
        if heard is not None:
            await self._speaker.stop()
            self.emit(wire.BargeIn())
            self._hand_mic("listen", self._listen(heard, source))
        elif isinstance(source, EchoCancelledSource) and source.failure:
            # From the next reply on, the plain microphone, as without echo cancellation: right
            # with earphones. Not for this reply: with speakers, Mei would hear itself at once.
            await source.stop()
            self._barge_source = self._source
            self.emit(wire.Failed(part="echo cancellation",
                                  message=f"{source.failure}, so talking over Mei works with earphones only"))

    async def _watch(self, hit, source: AudioSource, samples: int = CHUNK) -> list | None:
        """Read `source` in chunks of `samples` until `hit(chunk)`; returns the recent audio, the
        microphone still open for listening. None if the microphone closed first."""
        recent: collections.deque = collections.deque(maxlen=math.ceil(PREROLL_S * SAMPLE_RATE / samples))
        await source.start()
        async for chunk in source.chunks(samples):
            recent.append(chunk)
            if hit(chunk):
                return list(recent)
        return None

    # ── Speaking ─────────────────────────────────────────────────────────────

    def _spoke(self) -> None:
        self.emit(wire.Speaking())
        asyncio.ensure_future(self._aside_stop())  # an answer starting ends the tone or a check-in
        if self._mic_job == "wake":
            asyncio.ensure_future(self._release_then_watch())
        elif self._config is not None and self._config.barge_in and self._mic_task is None:
            self._hand_mic("barge", self._watch_barge_in())

    async def _release_then_watch(self) -> None:
        await self._release_mic()  # no wake word while Mei talks; talking over it is barge-in's job
        if self._config is not None and self._config.barge_in and self._speaker.speaking:
            self._hand_mic("barge", self._watch_barge_in())

    def _aside_started(self) -> None:
        if self._reading is not None:
            self.emit(wire.Reading(id=self._reading))
        if self._mic_job == "wake":  # "Hey Mei" doesn't listen to Mei reading
            asyncio.ensure_future(self._release_mic())

    def _aside_done(self) -> None:
        read_id, self._reading = self._reading, None
        if read_id is not None:
            self.emit(wire.ReadDone(id=read_id))
        self._rearm()

    async def _aside_stop(self) -> None:
        """Silence the tone, a check-in, or Read aloud (which then says it was stopped)."""
        if self._aside is None:
            return
        if self._aside.pending:
            await self._aside.stop()
        read_id, self._reading = self._reading, None
        if read_id is not None:
            self.emit(wire.ReadDone(id=read_id, stopped=True))

    def _spoken(self) -> None:
        self.emit(wire.Spoken())
        asyncio.ensure_future(self._after_speaking())

    async def _after_speaking(self) -> None:
        if self._mic_job == "barge":  # the barge-in watch has nothing left to watch
            await self._release_mic()
        self._rearm()

    async def _speaker_stop(self) -> bool:
        """Stop a reply, even one whose first sentence is still being synthesized. True: there was one."""
        if self._speaker is None or not self._speaker.pending:
            return False
        if self._mic_job == "barge":
            await self._release_mic()
        await self._speaker.stop()
        return True


def tone(rate: int = 24_000) -> Speech:
    """Mei heard you and is working: two soft notes, a fifth apart, faded in and out (~0.3 s, quiet)."""
    notes = []
    for hz in (587.33, 880.0):  # D5, A5
        t = np.arange(int(0.14 * rate)) / rate
        fade = np.minimum(1.0, np.minimum(t, t[::-1]) / 0.03)
        notes.append((0.06 * np.sin(2 * np.pi * hz * t) * fade).astype(np.float32))
    return Speech(np.concatenate(notes), rate)


def diagnose() -> wire.Diagnosis:
    """What the worker can reach from where it runs: in its jail, none of these."""
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=1).close()
        network = True
    except OSError:
        network = False
    home = os.environ.get("MEI_PERSON_HOME", "")
    runtime = f"/run/user/{os.getuid()}"
    return wire.Diagnosis(network=network,
                          home_visible=bool(home) and any(os.path.exists(os.path.join(home, p))
                                                          for p in ("Documents", "Downloads", ".ssh", ".config")),
                          session_bus=os.path.exists(f"{runtime}/bus"),
                          pulse_socket=os.path.exists(f"{runtime}/pulse/native"))


async def main() -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="voice worker: %(message)s")
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=wire.MAX_LINE)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    worker = Worker()
    while line := await reader.readline():
        try:
            cmd = wire.command(line)
        except msgspec.DecodeError as e:
            worker.emit(wire.Failed(part="protocol", message=str(e)[:200]))
            continue
        if not await worker.handle(cmd):
            break
    await worker.handle(wire.Quit())
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
