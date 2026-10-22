"""Voice in the core (§11.2, decision 0017): runs the voice worker, turns what the person says into
requests, and speaks the replies.

The person presses the voice shortcut (or says "Hey Mei"); what they say becomes an ordinary
request, marked as spoken, so the model answers briefly; the reply's text is spoken sentence by
sentence as it streams. Pressing again while listening ends the utterance; while Mei speaks, it
stops it and listens. "Stop" or "cancel that" is matched here, not by the model, and stops the
task. After a spoken reply Mei listens for a few seconds more, so a follow-up needs no shortcut.
The microphone is closed while the screen is locked.

The controller sees the engine's events by being one of its publishers (core/fanout.py).
"""

import asyncio
import logging
import re
import time
from collections.abc import Callable
from pathlib import Path

from mei.core.states import TERMINAL
from mei.protocol import Envelope, ProtocolError, SubmitInputArgs, TaskCommandArgs, VoiceSettings
from mei.store import repo
from mei.store.db import new_id

from . import remote, wire
from .cloud import CloudSpeech
from .models import KOKORO, KROKO, KWS, PIPER, SILERO, have, models_dir
from .parts import VoiceError
from .speakable import Sentences

log = logging.getLogger("mei.voice")
STOP = re.compile(r"^\s*(stop|cancel|cancel (that|it)|never ?mind|forget it|stop (that|it)|that's enough)[.!]?\s*$", re.I)
FOLLOW_UP_WINDOW_S = 300  # the wake word continues the last spoken conversation within this time
RESTARTS = (1.0, 5.0, 30.0)  # back-off when the worker dies

States = ("off", "unavailable", "starting", "idle", "listening", "thinking", "speaking", "suspended")


class VoiceController:
    def __init__(self, engine, emit: Callable[[str, dict], None], argv: Callable[[VoiceSettings, Path], list[str]],
                 models: Path | None = None, load_extra: dict | None = None, cloud: CloudSpeech | None = None) -> None:
        """`emit(type, payload)` sends an ephemeral event to clients; `argv(settings, models)` is the
        command that starts the worker (in its jail). `cloud`: cloud speech, when chosen in Settings.
        `load_extra`: test backends (recorded audio)."""
        self._engine = engine
        self._cloud = cloud
        self._emit = emit
        self._argv = argv
        self._models = models or models_dir()
        self._load_extra = load_extra or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._settings = VoiceSettings()
        self.state = "off"
        self.note = ""  # why voice is unavailable, or a fallback worth saying
        self._conversation: str | None = None
        self._last_spoken_at = 0.0
        self._task: str | None = None  # the request being answered out loud
        self._message: str | None = None  # its assistant message streaming now
        self._fed = 0  # characters of that message given to `_sentences`
        self._sentences = Sentences()
        self._follow_up = False
        self._locked = False
        self._stopping = False
        self._restarts = 0
        self._ready = asyncio.Event()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def apply(self, settings: VoiceSettings) -> None:
        """Start, reload, or stop the worker to match the settings."""
        changed = settings != self._settings
        self._settings = settings
        if not settings.enabled:
            await self.stop()
            self._set("off")
            return
        missing = [m.part for m in self.needed() if not have(m, self._models)]
        if missing:
            await self.stop()
            self._set("unavailable", f"download the voice models first ({', '.join(missing)})")
            return
        if self._proc is None:
            await self._spawn()
        elif changed:
            await self._load()

    def needed(self):
        """The local models these settings use: voice detection and Kroko always (Kroko shows what
        is heard live, even when a cloud provider does the final text)."""
        s = self._settings
        speech = {"piper": [PIPER.get(s.voice, PIPER["amy"])], "kokoro": [KOKORO]}.get(s.tts, [])
        return (SILERO, KROKO, *speech, *([KWS] if s.wake_word else []))

    async def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        self._stopping = True
        try:
            if proc.stdin is not None and not proc.stdin.is_closing():
                proc.stdin.write(wire.encode(wire.Quit()))
                proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), 5)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        finally:
            if self._reader is not None:
                await asyncio.gather(self._reader, return_exceptions=True)
            self._stopping = False

    async def _spawn(self) -> None:
        self._set("starting")
        self._ready.clear()
        argv = self._argv(self._settings, self._models)
        try:
            self._proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE,
                                                              stdout=asyncio.subprocess.PIPE,
                                                              stderr=asyncio.subprocess.PIPE, limit=wire.MAX_LINE)
        except OSError as e:
            self._set("unavailable", f"the voice worker couldn't start: {e.strerror}")
            return
        self._reader = asyncio.ensure_future(self._read(self._proc))
        asyncio.ensure_future(self._log_stderr(self._proc))
        await self._load()

    async def _load(self) -> None:
        s = self._settings
        stt = "kroko" if s.stt == "local" else "core"
        tts = s.tts if s.tts in ("piper", "kokoro") else "core"
        await self._send(wire.Load(models=str(self._models), stt=stt, tts=tts, voice=s.voice, speaker=s.kokoro_speaker,
                                   speed=s.speed, device=s.device, wake=s.wake_word, barge_in=s.barge_in,
                                   end_silence_s=s.end_silence_ms / 1000, mic=s.mic, output=s.output,
                                   **self._load_extra))

    async def wait_ready(self, timeout: float = 60.0) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout)

    # ── What the person does ─────────────────────────────────────────────────

    async def listen(self, conversation_id: str | None) -> None:
        """The voice shortcut or mic button: start listening; while listening, done talking."""
        if self.state == "listening":
            await self._send(wire.DoneTalking())
            return
        if self.state not in ("idle", "speaking", "thinking"):
            raise ProtocolError("Unavailable", self.note or f"voice is {self.state}")
        self._conversation = conversation_id
        self._follow_up = False
        await self._send(wire.Listen())

    async def hush(self) -> None:
        """Stop listening or speaking (Esc, the Stop button)."""
        self._follow_up = False
        if self.state == "listening":
            await self._send(wire.CancelListen())
            self._set("idle")
        elif self.state == "speaking":
            self._task = None
            await self._send(wire.StopSpeaking())

    async def set_locked(self, locked: bool) -> None:
        """The screen locked or unlocked: nothing listens while it is locked."""
        self._locked = locked
        if self._proc is None:
            return
        await self._send(wire.Suspend() if locked else wire.Resume())
        if not locked:
            self._set("idle")

    # ── The worker ───────────────────────────────────────────────────────────

    async def _send(self, cmd: wire.Command) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdin.is_closing():
            raise ProtocolError("Unavailable", self.note or "voice isn't running")
        proc.stdin.write(wire.encode(cmd))
        await proc.stdin.drain()

    async def _read(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout is not None
        while line := await proc.stdout.readline():
            try:
                event = wire.event(line)
            except Exception:  # noqa: BLE001  a line that isn't an event: log it, keep going
                log.warning("voice worker said something unexpected: %r", line[:200])
                continue
            try:
                await self._on_worker(event)
            except Exception:
                log.exception("handling a voice event failed")
        if self._stopping or self._proc is not proc:
            return
        self._proc = None
        await self._restart()

    async def _restart(self) -> None:
        if self._restarts >= len(RESTARTS):
            self._set("unavailable", "the voice worker keeps stopping; see the Mei log")
            return
        delay = RESTARTS[self._restarts]
        self._restarts += 1
        self._set("unavailable", f"voice stopped; restarting in {delay:.0f} s")
        await asyncio.sleep(delay)
        if self._settings.enabled and self._proc is None:
            await self._spawn()

    async def _log_stderr(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr is not None
        while line := await proc.stderr.readline():
            log.info("%s", line.decode("utf-8", "replace").rstrip()[:500])

    async def _on_worker(self, event: wire.Event) -> None:
        match event:
            case wire.Ready():
                self._restarts = 0
                note = event.note or ""
                self._set("suspended" if self._locked else "idle", note)
                self._ready.set()
                if self._locked:
                    await self._send(wire.Suspend())
            case wire.Failed(part=part, message=message):
                self._set("unavailable" if not self._ready.is_set() else self.state, f"{part}: {message}")
                self._ready.set()
            case wire.Listening():
                self._set("listening")
            case wire.Partial(text=text):
                self._emit("voice.partial", {"text": text, "final": False})
            case wire.Final(text=text):
                self._emit("voice.partial", {"text": text, "final": True})
                await self._heard(text)
            case wire.NoSpeech():
                self._follow_up = False
                self._set("idle")
            case wire.Speaking():
                self._set("speaking")
            case wire.Spoken(stopped=stopped):
                self._last_spoken_at = time.monotonic()
                if stopped or not self._follow_up:
                    self._set("idle")
                else:  # a follow-up needs no shortcut: listen a few seconds more
                    self._follow_up = False
                    await self._send(wire.Listen())
            case wire.BargeIn():
                self._task = None
            case wire.Woke():
                if time.monotonic() - self._last_spoken_at > FOLLOW_UP_WINDOW_S:
                    self._conversation = None
            case wire.Suspended():
                self._set("suspended")
            case wire.Transcribe() | wire.Synthesize():
                asyncio.ensure_future(self._cloud_answer(event))

    async def _cloud_answer(self, request: wire.Transcribe | wire.Synthesize) -> None:
        """The worker asks for cloud speech (it has no network): answer it, or say what failed."""
        s = self._settings
        try:
            if self._cloud is None:
                raise VoiceError("cloud speech", "isn't available here")
            if isinstance(request, wire.Transcribe):
                text = await self._cloud.transcribe(s.stt, remote.samples(request.pcm))
                reply: wire.Command = wire.Transcript(id=request.id, text=text)
            else:
                speech = await self._cloud.synthesize(s.tts, request.text, s.cloud_voice)
                reply = wire.Audio(id=request.id, rate=speech.rate, pcm=remote.pcm(speech.samples))
        except VoiceError as e:
            self._set(self.state, e.message)
            reply = (wire.Transcript(id=request.id, error=e.message) if isinstance(request, wire.Transcribe)
                     else wire.Audio(id=request.id, error=e.message))
        await self._send_quietly(reply)

    async def _heard(self, text: str) -> None:
        """A finished utterance: stop the task, or ask Mei."""
        running = self._running_task()
        if STOP.match(text):
            if running is not None:
                self._engine.cancel(TaskCommandArgs(command_id=new_id(), task_id=running))
            self._set("idle")
            return
        try:
            reply = self._engine.submit_input(SubmitInputArgs(command_id=new_id(), text=text,
                                                              conversation_id=self._conversation, source="voice"))
        except ProtocolError as e:
            self._set("idle", e.message)
            return
        self._conversation = reply["conversation_id"]
        self._task = reply["task_id"] if self._settings.speak_replies else None
        self._message, self._fed, self._sentences = None, 0, Sentences()
        self._set("thinking" if self._task else "idle")

    def _running_task(self) -> str | None:
        if self._conversation is None:
            return None
        row = self._engine.store.read_one(
            "SELECT id, state FROM tasks WHERE conversation_id = ? ORDER BY created_at DESC LIMIT 1", (self._conversation,))
        return row["id"] if row is not None and row["state"] not in TERMINAL else None

    # ── Publisher: the engine's events ───────────────────────────────────────

    def publish(self, events: list[Envelope]) -> None:
        for event in events:
            if event.type == "config.changed":
                asyncio.ensure_future(self.apply(repo.get_config(self._engine.store)[1].voice))
            elif self._task is not None and event.task_id == self._task:
                self._on_task_event(event)

    def publish_ephemeral(self, event: Envelope) -> None:
        if self._task is None or event.task_id != self._task or event.type != "message.delta":
            return
        p = event.payload
        if p.get("message_id") != self._message:
            self._message, self._fed = p.get("message_id"), 0
        text = p.get("text") or ""
        self._fed += len(text)
        self._say(self._sentences.feed(text))

    def _on_task_event(self, event: Envelope) -> None:
        p = event.payload
        if event.type == "message.completed" and p["message"]["role"] == "assistant":
            content = p["message"]["content"]
            if p["message"]["id"] != self._message:  # streamed without deltas reaching us
                self._message, self._fed = p["message"]["id"], 0
            self._say(self._sentences.feed(content[self._fed:] + "\n"))
            self._fed = len(content)
        elif event.type == "approval.requested":
            self._say(["I need your OK for that. It's on screen."])
        elif event.type == "input.requested":
            self._say([p["request"]["spec"]["question"]])
        elif event.type == "task.finished":
            sentences = self._sentences.flush()
            if p.get("state") == "FAILED":
                sentences.append("Sorry, I couldn't do that.")
            self._say(sentences)
            self._task = None
            self._follow_up = p.get("state") == "COMPLETED"
            asyncio.ensure_future(self._send_quietly(wire.End()))

    def _say(self, sentences: list[str]) -> None:
        for sentence in sentences:
            asyncio.ensure_future(self._send_quietly(wire.Say(text=sentence)))

    async def _send_quietly(self, cmd: wire.Command) -> None:
        try:
            await self._send(cmd)
        except ProtocolError as e:
            log.warning("voice: couldn't send %s: %s", type(cmd).__name__, e.message)

    def _set(self, state: str, note: str | None = None) -> None:
        if note is not None:
            self.note = note
        if state == self.state and note is None:
            return
        self.state = state
        self._emit("voice.state", {"state": state, "note": self.note, "conversation_id": self._conversation})
