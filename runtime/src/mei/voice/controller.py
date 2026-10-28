"""Voice in the core (§11.2, decision 0017): runs the voice worker, turns what the person says into
requests, and speaks the replies.

The person presses the voice shortcut (or the voice button, or says "Hey Mei"); what they say
becomes an ordinary request, marked as spoken, so the model answers briefly; the reply's text is
spoken sentence by sentence as it streams. "Stop" or "cancel that" is matched here, not by the
model, and stops the task.

Listening goes on until the person ends it (decision 0026): a conversation listens again after
each reply. Started with the voice button, it goes on until closed; started with the shortcut or
"Hey Mei", until 30 s pass with nothing said. Dictation (the mic) keeps writing what's said into
the message box, across pauses, until the mic is pressed again. Pressing again while someone talks
sends what they said at once; pressing with nothing said closes it. The microphone is closed while
the screen is locked, and while another app records; listening comes back after both.

The controller sees the engine's events by being one of its publishers (core/fanout.py).
"""

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from mei.core.states import TERMINAL
from mei.protocol import (Attachment, Envelope, ProtocolError, ResolveApprovalArgs, SubmitInputArgs,
                          TaskCommandArgs, VoiceSettings)
from mei.store import repo
from mei.store.db import new_id

import httpx

from mei.desktop.run import ToolFailed
from mei.desktop.sound import SOURCE, Wpctl, audio_devices

from . import boost, cleanup, engines, jail, remote, wire
from .cloud import TTS, CloudSpeech
from . import mic_users
from .mic_users import MicUsers
from .catalog import GPU_ENGINE, ModelStore
from .models import KOKORO_VOICES, PIPER, have, kokoro_label, models_dir
from .parts import VoiceError
from .phrases import CONFIRM, DECLINE, STOP, speakable_title, spoken_ok  # noqa: F401  (tests import them here)
from .replies import Replies
from .speakable import Sentences
from .waiting import Waiting

log = logging.getLogger("mei.voice")
FOLLOW_UP_WINDOW_S = 300  # the wake word continues the last spoken conversation within this time
RESTARTS = (1.0, 5.0, 30.0)  # back-off when the worker dies
CLOUD_FALLBACK = {"hearing": "this computer wrote down what you said", "speaking": "Mei spoke with this computer's voice"}
OVERDRIVEN_DB = -20.0  # silence louder than this, or any real clipping, breaks voice detection (spike 0c)
OVERDRIVEN_CLIP_PCT = 0.5
FIXED_LEVEL_PCT = 50  # spike 0c: the laptop mic was clean at 51 %

PAUSED_NOTE = "Paused while another app uses the microphone"
MIC_USERS_NOTES = (PAUSED_NOTE, "Mei can't make way for other apps recording")

States = ("off", "unavailable", "starting", "idle", "listening", "thinking", "speaking", "suspended", "paused")
# How a conversation started, and so when it ends (decision 0026): "button", when closed; "quiet"
# (the shortcut, "Hey Mei"), after QUIET_S with nothing said; "dictate", when the mic is pressed again.
Session = Literal["button", "quiet", "dictate"]
QUIET_S = 30.0
BOOST_FRESH_S = 60.0  # the words Mei listens for are gathered again after this, when listening starts


class VoiceController:
    def __init__(self, engine, emit: Callable[[str, dict], None],
                 argv: Callable[[VoiceSettings, Path, Path | None], list[str]], models: Path | None = None,
                 load_extra: dict | None = None, cloud: CloudSpeech | None = None,
                 client: httpx.AsyncClient | None = None,
                 gpu_engine_for: Callable[[str, str], Path | None] = jail.gpu_engine_for,
                 pw_dump: tuple[str, ...] = mic_users.ARGV) -> None:
        """`emit(type, payload)` sends an ephemeral event to clients; `argv(settings, models, gpu engine)`
        is the command that starts the worker (in its jail, given the GPU engine when it may use it).
        `cloud`: cloud speech, when chosen in Settings. `load_extra`: test backends (recorded audio).
        `pw_dump`: what follows PipeWire's graph for other apps recording (tests give a stand-in)."""
        self._engine = engine
        self._gpu_engine_for = gpu_engine_for
        self._gpu_engine: Path | None = None  # what the running worker's jail was given
        self._cloud = cloud
        self._mic_level: asyncio.Future | None = None
        self._emit = emit
        self._argv = argv
        self._models = models or models_dir()
        self._store = ModelStore(self._models, client, lambda: self.apply(self._settings))
        self._load_extra = load_extra or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._settings = VoiceSettings()
        self.state = "off"
        self.note = ""  # why voice is unavailable, or a fallback worth saying
        self._cloud_note = ""  # the note while cloud speech fails and this computer stands in
        self._conversation: str | None = None
        self._last_spoken_at = 0.0
        self._session: Session | None = None  # listening goes on until this ends
        self._speech_heard = False  # in the utterance being heard now
        self._dictating = False  # this utterance goes into the input box, not to Mei
        self._attachment: Attachment | None = None  # dropped on Mei during a conversation: goes with the next request
        self._locked = False
        self._stopping = False
        self._restarts = 0
        self._version_restarted = False  # a worker of another version was started again once
        self._reading: str | None = None  # the message Read aloud is reading
        self._ready = asyncio.Event()
        # "Hey Mei" pauses while another app records (decision 0025).
        self._mic_users = MicUsers(self._others_recording, self._mic_users_trouble, pw_dump)
        self._replies = Replies(engine, self._say, self._say_end)
        self._cleanup = cleanup.default_chain()  # what was heard, tidied; the raw words go along (decision 0029)
        self._boost_at = -BOOST_FRESH_S  # when the words Mei listens for were last gathered
        # The tone, then check-ins, while Mei works on a spoken request (decision 0029).
        self._waiting = Waiting(lambda text: asyncio.ensure_future(self._send_quietly(wire.Cue(text=text))))

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def apply(self, settings: VoiceSettings) -> None:
        """Start, reload, or stop the worker to match the settings."""
        changed = settings != self._settings
        if settings.boost_words != self._settings.boost_words:
            self._boost_at = -BOOST_FRESH_S
        self._settings = settings
        if not settings.enabled:
            await self.stop()
            self._set("off")
            return
        try:
            await self._apply(settings, changed)
        finally:
            await self._follow_mic_users()

    async def _apply(self, settings: VoiceSettings, changed: bool) -> None:
        missing = [m.part for m in engines.needed(self._settings, required_only=True) if not have(m, self._models)]
        if missing:
            await self.stop()
            self._set("unavailable", f"download the voice models first ({', '.join(missing)})")
            return
        if self._proc is None:
            await self._spawn()
        elif self._gpu_engine_for(settings.tts, settings.device) != self._gpu_engine:
            await self.stop()  # the jail itself changes: the GPU joins or leaves it
            await self._spawn()
        elif changed:
            await self._load()

    def needed(self):
        """The local models these settings use (engines.py)."""
        return engines.needed(self._settings)

    async def stop(self) -> None:
        await self._mic_users.stop()
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
        self._gpu_engine = self._gpu_engine_for(self._settings.tts, self._settings.device)
        argv = self._argv(self._settings, self._models, self._gpu_engine)
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
                                   echo_cancel=s.echo_cancel,
                                   end_silence_s=s.end_pause_ms / 1000, quiet_s=QUIET_S, mic=s.mic,
                                   output=s.output,
                                   gpu_engine=str(self._gpu_engine or ""), gpu_idle_s=s.gpu_idle_min * 60,
                                   **self._load_extra))

    async def wait_ready(self, timeout: float = 60.0) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout)

    # ── Models, the microphone, the speakers (setup and Settings) ────────────

    def models(self) -> dict:
        return {"state": self.state, "note": self.note, **self._store.listing(self._settings),
                "voices": voice_choices(), "engines": engines.listing(),
                "boost": self.boost_words()}

    def download(self, ids: list[str]) -> None:
        """Fetch these models in the background (progress in `models()`), then start voice if it is on."""
        self._store.download(ids)

    async def remove(self, ids: list[str]) -> None:
        """Delete downloaded models (or the GPU engine); voice then carries on without them."""
        if GPU_ENGINE in ids and self._gpu_engine is not None:
            self._store.check(ids)
            await self.stop()  # nothing may run from the engine while it is deleted
        await self._store.remove(ids)

    async def check_mic(self, seconds: float = 3.0) -> dict:
        """The microphone's level in silence, and whether it is overdriven. Numbers only."""
        if self.state not in ("idle", "speaking"):
            raise ProtocolError("Unavailable", self.note or f"voice is {self.state}")
        self._mic_level = asyncio.get_running_loop().create_future()
        await self._send(wire.MeasureMic(seconds=seconds))
        try:
            level: wire.MicLevel = await asyncio.wait_for(self._mic_level, seconds + 10)
        except TimeoutError:
            raise ProtocolError("Unavailable", "the microphone didn't answer") from None
        finally:
            self._mic_level = None
        return {"db": level.db, "peak_db": level.peak_db, "clipped_pct": level.clipped_pct,
                "overdriven": level.db > OVERDRIVEN_DB or level.clipped_pct > OVERDRIVEN_CLIP_PCT}

    async def fix_mic(self) -> dict:
        """Lower an overdriven microphone's capture level (the chosen one, or the default), then
        measure again."""
        try:
            node = SOURCE
            if self._settings.mic:
                mics = (await audio_devices())["mics"]
                node = next((str(d["id"]) for d in mics if d["name"] == self._settings.mic), SOURCE)
            await Wpctl(node=node).set(FIXED_LEVEL_PCT, muted=False)
        except Exception as e:  # noqa: BLE001  wpctl missing or refused
            raise ProtocolError("Unavailable", f"couldn't change the microphone's level: {e}") from None
        return await self.check_mic()

    async def devices(self) -> dict:
        """The microphones and speakers to choose from, by node name and label."""
        try:
            found = await audio_devices()
        except ToolFailed as e:
            raise ProtocolError("Unavailable", f"couldn't list audio devices: {e}") from None
        return {key: [{"name": d["name"], "label": d["label"]} for d in found[key]] for key in ("mics", "outputs")}

    async def test_speaker(self) -> None:
        await self._send(wire.Say(text="Hi, this is how I'll sound when I answer you."))
        await self._send(wire.End())

    # ── What the person does ─────────────────────────────────────────────────

    async def listen(self, conversation_id: str | None, *, dictate: bool = False, by: str = "shortcut") -> None:
        """The voice shortcut (`by` "shortcut") or voice button ("button"): talk with Mei;
        `dictate` (the mic button): only to write down what's said. While listening: if someone
        is talking, what they said is sent at once; if not (or when dictating), it ends."""
        if self.state == "listening":
            if self._session == "dictate":
                # Done dictating: the words still being heard are dictation too, so `_dictating`
                # stays until they arrive (cleared, they would go to Mei as a request).
                self._session = None
                await self._follow_mic_users()
            elif not self._speech_heard:
                await self._end_session()
            await self._send(wire.DoneTalking())
            return
        if self.state not in ("idle", "speaking", "thinking", "paused"):
            raise ProtocolError("Unavailable", self.note or f"voice is {self.state}")
        self._conversation = conversation_id
        self._dictating = dictate
        self._fresh_boost()
        await self._start_session("dictate" if dictate else "button" if by == "button" else "quiet")

    async def read_aloud(self, message_id: str, text: str) -> None:
        """A reply's Read aloud (decision 0030): read out on its own, not as Live. Voice's state doesn't
        change, nothing listens after, and talking doesn't interrupt it; its button (or Esc) stops
        it. Code and tables are left out with a note, as in spoken answers."""
        if self._session is not None or self.state in ("listening", "thinking", "speaking", "paused"):
            raise ProtocolError("Busy", "Live is on: end it to hear a reply read aloud")
        if self.state != "idle":
            raise ProtocolError("Unavailable", self.note or f"voice is {self.state}")
        reading = Sentences()
        self._reading = message_id
        await self._send(wire.ReadAloud(id=message_id, sentences=reading.feed(text + "\n") + reading.flush()))

    async def stop_reading(self) -> None:
        await self._send_quietly(wire.StopReading())

    def boost_words(self) -> dict[str, list[str]]:
        return boost.words(getattr(self._engine, "store", None), self._settings.boost_words)

    def _fresh_boost(self) -> None:
        """Gather the words Mei listens for again, if it has been a while (a few ms: app files, the store)."""
        now = time.monotonic()
        if now - self._boost_at < BOOST_FRESH_S:
            return
        self._boost_at = now
        try:
            found = self.boost_words()
        except Exception:  # noqa: BLE001  a broken app file or store: keep the words there were
            log.exception("gathering the words to listen for failed")
            return
        self._cleanup = cleanup.default_chain([*found["yours"], *found["learned"], *found["apps"]])

    def attach(self, attachment: Attachment | None) -> None:
        """Files or text dropped on Mei while talking with it: they go with what's said next (None: removed)."""
        self._attachment = attachment

    async def hush(self) -> None:
        """Close voice: stop listening or speaking, and listen no more (Esc, Stop, the voice button).
        A reply still being written is shown, not spoken."""
        await self._end_session()
        self._replies.follow(None)
        if self._reading is not None:
            await self._send_quietly(wire.StopReading())
        if self.state == "listening":
            await self._send(wire.CancelListen())
            self._set("idle")
        elif self.state == "speaking":
            await self._send(wire.StopSpeaking())
        elif self.state in ("thinking", "paused"):
            self._set("idle")

    async def set_locked(self, locked: bool) -> None:
        """The screen locked or unlocked: nothing listens while it is locked; a conversation or
        dictation that was going on listens again after (0018's rule, not an ending)."""
        self._locked = locked
        await self._follow_mic_users()
        if self._proc is None:
            return
        await self._send(wire.Suspend() if locked else wire.Resume())
        if not locked:
            self._set("idle")
            await self._go_on()

    # ── Listening that goes on (decision 0026) ───────────────────────────────

    async def _start_session(self, session: Session) -> None:
        """The person asked: listen now, even while another app records (only what Mei would do by
        itself waits for that)."""
        self._session = session
        await self._follow_mic_users()
        await self._mic_users.known()  # a call going on already doesn't stop this; one that starts later does
        await self._go_on(asked=True)

    async def _end_session(self) -> None:
        self._session, self._dictating = None, False
        await self._follow_mic_users()

    async def _go_on(self, asked: bool = False) -> None:
        """Listen (again) if a conversation or dictation is going on, unless the screen is locked
        or, without being `asked`, another app is recording (then it waits, and comes back when
        they're done)."""
        if self._session is None or self._locked or self._proc is None:
            return
        if self._mic_users.others and not asked:
            self._set("paused", PAUSED_NOTE)
            return
        self._speech_heard = False
        match self._session:
            case "dictate":
                await self._send(wire.Listen(no_speech_s=0, continuous=True))
            case "button":
                await self._send(wire.Listen(no_speech_s=0))
            case "quiet":
                await self._send(wire.Listen(no_speech_s=QUIET_S))

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

    async def _respawn(self) -> None:
        await self.stop()
        if self._settings.enabled:
            await self._spawn()

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
            case wire.Ready() if event.version != wire.VERSION:
                # A worker started from other code than this core's (Mei updated while running): it
                # would refuse what it doesn't know. Start it again, once; then say so.
                if self._version_restarted:
                    self._set("unavailable", "Mei was updated while running: log out and back in to use voice")
                    return
                self._version_restarted = True
                log.warning("voice worker speaks %s, the core %s: starting it again", event.version, wire.VERSION)
                asyncio.ensure_future(self._respawn())
            case wire.Ready():
                self._restarts = 0
                self._version_restarted = False
                if self._reading is not None:  # a new worker isn't reading anything
                    self._emit("voice.reading", {"message_id": self._reading, "reading": False})
                    self._reading = None
                note = event.note or ""
                # A reload (a setting changed) closed the microphone; a conversation or dictation
                # going on listens again rather than ending.
                resume = self._session is not None and not self._locked and self._ready.is_set()
                self._set(self.state if resume else "suspended" if self._locked else "idle", note)
                self._ready.set()
                if self._locked:
                    await self._send(wire.Suspend())
                if self._mic_users.others:  # the load re-armed the wake word
                    await self._send(wire.Arm(on=False))
                if resume:
                    await self._go_on()
            case wire.Failed(part=part, message=message):
                self._set("unavailable" if not self._ready.is_set() else self.state, f"{part}: {message}")
                self._ready.set()
            case wire.Listening():
                self._speech_heard = False
                self._set("listening", "" if self.note == PAUSED_NOTE else None)
            case wire.SpeechStarted():
                self._speech_heard = True
            case wire.Partial(text=text):
                self._emit("voice.partial", {"text": text, "final": False, "dictation": self._dictating})
            case wire.Final(text=raw):
                self._speech_heard = False
                text = self._cleanup(raw).text
                self._emit("voice.partial", {"text": text, "raw": raw, "final": True, "dictation": self._dictating})
                if self._dictating:  # the words go into the input box; the person sends them
                    if self._session != "dictate":  # the mic was pressed again: that was the last
                        self._dictating = False
                        self._set("idle")
                else:
                    await self._heard(text)
            case wire.NoSpeech():
                heard, self._speech_heard = self._speech_heard, False
                if self._session == "dictate":
                    return  # a cough, not words: dictation goes on
                if self._session == "quiet" and not heard:
                    await self._end_session()  # QUIET_S with nothing said: Mei goes offline
                if self._session is None:
                    self._dictating = False
                    self._set("idle")
                else:
                    await self._go_on()
            case wire.Speaking():
                self._set("speaking")
            case wire.Spoken(stopped=stopped):
                self._last_spoken_at = time.monotonic()
                if stopped:  # stopped to listen (the shortcut, barge-in) or closed (hush)
                    if self._session is None:
                        self._set("idle")
                elif self._session is not None:
                    await self._go_on()  # after each reply, listen again: no shortcut needed
                elif self._replies.asking:
                    await self._send(wire.Listen())  # the answer to a question Mei asked aloud
                else:
                    self._set("idle")
            case wire.BargeIn():
                self._replies.follow(None)
            case wire.Woke():
                self._fresh_boost()
                if time.monotonic() - self._last_spoken_at > FOLLOW_UP_WINDOW_S:
                    self._conversation = None
                self._dictating = False
                self._session = "quiet"  # the worker is listening already
                await self._follow_mic_users()
            case wire.Reading(id=read_id):
                self._emit("voice.reading", {"message_id": read_id, "reading": True})
            case wire.ReadDone(id=read_id):
                if self._reading == read_id:
                    self._reading = None
                self._emit("voice.reading", {"message_id": read_id, "reading": False})
            case wire.Suspended():
                self._set("suspended")
            case wire.Transcribe() | wire.Synthesize():
                asyncio.ensure_future(self._cloud_answer(event))
            case wire.MicLevel():
                if self._mic_level is not None and not self._mic_level.done():
                    self._mic_level.set_result(event)

    async def _cloud_answer(self, request: wire.Transcribe | wire.Synthesize) -> None:
        """The worker asks for cloud speech (it has no network): answer it, or say what failed. The
        worker then uses its local backend for that utterance or sentence, and the note says so
        until the cloud answers again."""
        s = self._settings
        hearing = isinstance(request, wire.Transcribe)
        try:
            if self._cloud is None:
                raise VoiceError("cloud speech", "isn't available here")
            if isinstance(request, wire.Transcribe):
                text = await self._cloud.transcribe(s.stt, remote.samples(request.pcm))
                reply: wire.Command = wire.Transcript(id=request.id, text=text)
            else:
                speech = await self._cloud.synthesize(s.tts, request.text, s.cloud_voice)
                reply = wire.Audio(id=request.id, rate=speech.rate, pcm=remote.pcm(speech.samples))
            if self._cloud_note and self.note == self._cloud_note:
                self._set(self.state, "")
            self._cloud_note = ""
        except VoiceError as e:
            self._cloud_note = f"{e.message}, so {CLOUD_FALLBACK['hearing' if hearing else 'speaking']}"
            self._set(self.state, self._cloud_note)
            reply = (wire.Transcript(id=request.id, error=e.message) if hearing
                     else wire.Audio(id=request.id, error=e.message))
        await self._send_quietly(reply)

    async def _heard(self, text: str) -> None:
        """A finished utterance: an answer to an approval Mei read out, stop the task, or ask Mei."""
        if self._replies.asking is not None and (CONFIRM.match(text) or DECLINE.match(text)):
            approval, self._replies.asking = self._replies.asking, None
            try:
                self._engine.resolve_approval(ResolveApprovalArgs(
                    command_id=new_id(), approval_id=approval, decision="allow" if CONFIRM.match(text) else "deny",
                    scope="once"), decided_by="voice")
            except ProtocolError as e:  # answered on screen meanwhile, or the action changed
                self._set("idle", e.message)
                await self._go_on()
                return
            self._set("thinking")
            return
        self._replies.asking = None  # anything else: the card stays on screen, and these words join the task
        running = self._running_task()
        if STOP.match(text):
            if running is not None:
                self._engine.cancel(TaskCommandArgs(command_id=new_id(), task_id=running))
            self._set("idle")
            await self._go_on()  # stopping the task isn't closing voice
            return
        attachment, self._attachment = self._attachment, None
        try:
            reply = self._engine.submit_input(SubmitInputArgs(command_id=new_id(), text=text, attachment=attachment,
                                                              conversation_id=self._conversation, source="voice"))
        except ProtocolError as e:
            self._attachment = attachment  # not sent: it goes with the next one
            self._set("idle", e.message)
            await self._go_on()
            return
        self._conversation = reply["conversation_id"]
        self._replies.follow(reply["task_id"] if self._settings.speak_replies else None)
        self._set("thinking" if self._replies.task else "idle")
        if self._replies.task is None:
            await self._go_on()  # the reply is only on screen: listen for the next thing at once

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
            else:
                self._replies.publish(event)

    def publish_ephemeral(self, event: Envelope) -> None:
        self._replies.delta(event)

    def _say(self, sentences: list[str]) -> None:
        for sentence in sentences:
            asyncio.ensure_future(self._send_quietly(wire.Say(text=sentence)))

    def _say_end(self) -> None:
        asyncio.ensure_future(self._send_quietly(wire.End()))

    async def _send_quietly(self, cmd: wire.Command) -> None:
        try:
            await self._send(cmd)
        except ProtocolError as e:
            log.warning("voice: couldn't send %s: %s", type(cmd).__name__, e.message)

    # ── Another app recording: Mei makes way (decisions 0025, 0026) ─────────

    async def _follow_mic_users(self) -> None:
        """Watch for other apps recording only while Mei would listen by itself: the wake word
        armed, or a conversation or dictation going on. Never otherwise."""
        s = self._settings
        if s.enabled and s.pause_for_apps and not self._locked and self._proc is not None \
                and (s.wake_word or self._session is not None):
            self._mic_users.start()
        elif self._mic_users.running:
            await self._mic_users.stop()
            if self.note.startswith(MIC_USERS_NOTES):
                self._set(self.state, "")

    def _others_recording(self, others: bool) -> None:
        """Another app started or stopped recording: let go of the microphone, or take it back.
        Pressing the shortcut or a button still listens meanwhile; only what Mei would do by
        itself (the wake word, listening again) waits."""
        asyncio.ensure_future(self._send_quietly(wire.Arm(on=not others)))
        if others and self._session is not None and self.state == "listening":
            asyncio.ensure_future(self._make_way())
        elif others:
            self._set(self.state, PAUSED_NOTE)
        elif self.state == "paused":
            asyncio.ensure_future(self._go_on())
        elif self.note == PAUSED_NOTE:
            self._set(self.state, "")

    async def _make_way(self) -> None:
        await self._send_quietly(wire.CancelListen())
        self._set("paused", PAUSED_NOTE)

    def _mic_users_trouble(self, message: str) -> None:
        if message:
            self._set(self.state, f"{MIC_USERS_NOTES[1]}: {message}")
        elif self.note.startswith(MIC_USERS_NOTES[1]):
            self._set(self.state, "")

    def _set(self, state: str, note: str | None = None) -> None:
        if note is not None:
            self.note = note
        if state == self.state and note is None:
            return
        if state != self.state:
            if state == "thinking" and self._replies.task is not None:
                self._waiting.start()
            else:
                self._waiting.stop()
        self.state = state
        self._emit("voice.state", {"state": state, "note": self.note, "conversation_id": self._conversation,
                                   "dictating": self._dictating})  # the UI follows this rather than guessing


def voice_choices() -> dict[str, list[dict]]:
    """Who can speak, per speech choice, by the id the settings keep: Piper's voice, Kokoro's speaker
    number, a cloud provider's voice name ("" for its default)."""
    choices = {"piper": [{"id": key, "label": m.part.removeprefix("voice: ")} for key, m in PIPER.items()],
               "kokoro": [{"id": str(i), "label": kokoro_label(v)} for i, v in enumerate(KOKORO_VOICES)]}
    for key, end in TTS.items():
        choices[key] = [{"id": "", "label": f"{end.voice.capitalize()} (default)"}] + [
            {"id": v, "label": v.capitalize()} for v in end.voices]
    return choices
