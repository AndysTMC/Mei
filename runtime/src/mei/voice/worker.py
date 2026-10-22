"""The voice worker (§5.4, decision 0017): microphone, speakers, and the local voice models, in a
jail with no network and no files of the person's (jail.py). It decides nothing about tasks: the
core tells it to listen and what to say, and it reports what it hears.

    python -m mei.voice.worker      (JSON lines: commands on stdin, events on stdout; wire.py)

Only one thing reads the microphone at a time: listening, the barge-in watch while speaking, or
the wake word while armed. Barge-in and wake hand the open microphone straight to listening, with
the audio they already heard, so the first words aren't lost.
"""

import asyncio
import collections
import contextlib
import logging
import os
import socket
import sys
from pathlib import Path

import msgspec
import numpy as np

from . import local, pipeline, remote, wire
from .parts import SAMPLE_RATE, AudioSink, AudioSource, VoiceError, level_db
from .pipewire import PipeWireSink, PipeWireSource
from .recorded import CaptureSink, RecordedSource

log = logging.getLogger("mei.voice")
BARGE_GRACE_S = 0.3  # after speech starts, before talking over it counts (the Hermes lesson, §11.4)
BARGE_SPEECH_S = 0.2  # speech this long stops Mei
PREROLL_CHUNKS = 8  # ~0.8 s of the barge-in or wake audio handed to listening


class Worker:
    def __init__(self, out=None) -> None:
        self._out = out or sys.stdout.buffer
        self._source: AudioSource | None = None
        self._sink: AudioSink | None = None
        self._vad: local.SileroVad | None = None
        self._wake: local.SherpaWake | None = None
        self._listener: pipeline.Listener | None = None
        self._speaker: pipeline.Speaker | None = None
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
                    if await self._speaker_stop():  # talking while Mei speaks: it stops for you
                        self.emit(wire.Spoken(stopped=True))
                    await self._take_mic("listen", self._listen())
            case wire.DoneTalking():
                if self._listener is not None:
                    self._listener.finish()
            case wire.CancelListen():
                await self._release_mic()
                self._rearm()
            case wire.Say(text=text):
                if self._ready() and not self._suspended and text.strip():
                    self._speaker.say(text)
            case wire.End():
                if self._ready() and not self._suspended:
                    self._speaker.end()
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
                return False
        return True

    def _ready(self) -> bool:
        if self._listener is None or self._speaker is None:
            self.emit(wire.Failed(part="voice", message="not loaded"))
            return False
        return True

    async def _load(self, cfg: wire.Load) -> None:
        root = Path(cfg.models)
        try:
            self._vad = local.SileroVad(root)
            stt = local.KrokoStt(root) if cfg.stt == "kroko" or local.have_kroko(root) else None
            if cfg.stt == "core":
                stt = remote.CoreStt(self._link, local=stt)
            if cfg.tts == "kokoro":
                tts, device, note = local.kokoro(root, cfg.speaker, cfg.speed, cfg.device)
            elif cfg.tts == "core":  # Piper says what the cloud can't
                fallback = local.piper(root, cfg.voice, cfg.speed) if local.have_piper(root, cfg.voice) else None
                tts, device, note = remote.CoreTts(self._link, fallback), "cloud", ""
            else:
                tts, device, note = local.piper(root, cfg.voice, cfg.speed), "cpu", ""
            self._wake = local.SherpaWake(root, Path("/tmp"), cfg.wake_threshold) if cfg.wake else None
        except VoiceError as e:
            self.emit(wire.Failed(part=e.part, message=e.message))
            return
        except Exception as e:  # noqa: BLE001  a model that won't load: say which part, keep running
            self.emit(wire.Failed(part="voice", message=str(e)[:300]))
            return
        self._source = RecordedSource(Path(cfg.source_file), cfg.source_realtime) if cfg.source_file \
            else PipeWireSource(cfg.mic)
        self._sink = CaptureSink(Path(cfg.sink_file)) if cfg.sink_file else PipeWireSink(cfg.output)
        ep = pipeline.Endpointing(end_silence_s=cfg.end_silence_s)
        self._listener = pipeline.Listener(self._source, self._vad, stt, ep)
        self._speaker = pipeline.Speaker(tts, self._sink, on_start=self._spoke, on_done=self._spoken,
                                         on_error=lambda e: self.emit(wire.Failed(part=e.part, message=e.message)))
        self._config = cfg
        self._armed = cfg.wake and self._wake is not None
        self.emit(wire.Ready(stt=stt.name, tts=tts.name, device=device, note=note, wake=self._wake is not None))
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
        if self._source is not None:
            await self._source.stop()

    def _rearm(self) -> None:
        """Back to waiting for the wake word, if it is on and nothing else holds the microphone."""
        if self._armed and not self._suspended and self._mic_task is None and self._wake is not None \
                and not (self._speaker and self._speaker.speaking):
            self._hand_mic("wake", self._wait_for_wake())

    async def _listen(self, preroll: list | None = None) -> None:
        task = asyncio.current_task()
        self.emit(wire.Listening())
        try:
            async for heard in self._listener.listen(preroll):
                match heard:
                    case pipeline.SpeechStarted():
                        self.emit(wire.SpeechStarted())
                    case pipeline.Partial(text=text):
                        self.emit(wire.Partial(text=text))
                    case pipeline.Final(text=text):
                        self.emit(wire.Final(text=text))
                    case pipeline.NoSpeech():
                        self.emit(wire.NoSpeech())
        except VoiceError as e:
            self.emit(wire.Failed(part=e.part, message=e.message))
        finally:
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
        heard = await self._watch(self._wake.heard)
        if heard is not None:
            self._wake.reset()
            self.emit(wire.Woke())
            self._hand_mic("listen", self._listen(heard))

    async def _watch_barge_in(self) -> None:
        loop = asyncio.get_running_loop()
        run = [0.0]

        def talking_over(chunk) -> bool:
            if loop.time() - self._speaker.started_at < BARGE_GRACE_S:
                run[0] = 0.0
                return False
            run[0] = run[0] + len(chunk) / SAMPLE_RATE if self._vad.is_speech(chunk) else 0.0
            return run[0] >= BARGE_SPEECH_S

        self._vad.reset()
        heard = await self._watch(talking_over)
        if heard is not None:
            await self._speaker.stop()
            self.emit(wire.BargeIn())
            self._hand_mic("listen", self._listen(heard))

    async def _watch(self, hit) -> list | None:
        """Read the microphone until `hit(chunk)`; returns the recent audio, the microphone still
        open for listening. None if the microphone closed first."""
        recent: collections.deque = collections.deque(maxlen=PREROLL_CHUNKS)
        await self._source.start()
        async for chunk in self._source.chunks():
            recent.append(chunk)
            if hit(chunk):
                return list(recent)
        return None

    # ── Speaking ─────────────────────────────────────────────────────────────

    def _spoke(self) -> None:
        self.emit(wire.Speaking())
        if self._mic_job == "wake":
            asyncio.ensure_future(self._release_then_watch())
        elif self._config is not None and self._config.barge_in and self._mic_task is None:
            self._hand_mic("barge", self._watch_barge_in())

    async def _release_then_watch(self) -> None:
        await self._release_mic()  # no wake word while Mei talks; talking over it is barge-in's job
        if self._config is not None and self._config.barge_in and self._speaker.speaking:
            self._hand_mic("barge", self._watch_barge_in())

    def _spoken(self) -> None:
        self.emit(wire.Spoken())
        asyncio.ensure_future(self._after_speaking())

    async def _after_speaking(self) -> None:
        if self._mic_job == "barge":  # the barge-in watch has nothing left to watch
            await self._release_mic()
        self._rearm()

    async def _speaker_stop(self) -> bool:
        if self._speaker is None or not self._speaker.speaking:
            return False
        if self._mic_job == "barge":
            await self._release_mic()
        await self._speaker.stop()
        return True


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
