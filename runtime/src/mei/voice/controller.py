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
import json
import logging
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path

from mei.core.states import TERMINAL
from mei.protocol import (Envelope, ProtocolError, ResolveApprovalArgs, SubmitInputArgs, TaskCommandArgs,
                          VoiceSettings)
from mei.store import repo
from mei.store.db import new_id

import httpx

from mei.desktop.run import ToolFailed
from mei.desktop.sound import SOURCE, Wpctl, audio_devices

from . import download, gpu_engine, jail, remote, wire
from .cloud import TTS, CloudSpeech
from .models import CATALOG, KOKORO, KOKORO_VOICES, KROKO, KWS, PIPER, SILERO, have, kokoro_label, models_dir
from .parts import VoiceError
from .speakable import Sentences

log = logging.getLogger("mei.voice")
STOP = re.compile(r"^\s*(stop|cancel|cancel (that|it)|never ?mind|forget it|stop (that|it)|that's enough)[.!]?\s*$", re.I)
# Spoken approval (§11.6): only this explicit phrase, after Mei has read the action back.
CONFIRM = re.compile(r"^\s*(yes|yeah|yep)[,.]?\s+(do it|go ahead)[.!]?\s*$", re.I)
DECLINE = re.compile(r"^\s*(no|nope|don'?t|do not)([,.]?\s+(do it|don'?t|thanks|thank you))?[.!]?\s*$", re.I)
_HOME_PATH = re.compile(r"~/(?:([^/\s]+)/)*([^/\s]+)")
FOLLOW_UP_WINDOW_S = 300  # the wake word continues the last spoken conversation within this time
RESTARTS = (1.0, 5.0, 30.0)  # back-off when the worker dies
GPU_ENGINE = "gpu-engine"  # the GPU engine's id among the models (it is downloaded the same way)
CLOUD_FALLBACK = {"hearing": "this computer wrote down what you said", "speaking": "Mei spoke with this computer's voice"}
OVERDRIVEN_DB = -20.0  # silence louder than this, or any real clipping, breaks voice detection (spike 0c)
OVERDRIVEN_CLIP_PCT = 0.5
FIXED_LEVEL_PCT = 50  # spike 0c: the laptop mic was clean at 51 %

States = ("off", "unavailable", "starting", "idle", "listening", "thinking", "speaking", "suspended")


class VoiceController:
    def __init__(self, engine, emit: Callable[[str, dict], None],
                 argv: Callable[[VoiceSettings, Path, Path | None], list[str]], models: Path | None = None,
                 load_extra: dict | None = None, cloud: CloudSpeech | None = None,
                 client: httpx.AsyncClient | None = None,
                 gpu_engine_for: Callable[[str, str], Path | None] = jail.gpu_engine_for) -> None:
        """`emit(type, payload)` sends an ephemeral event to clients; `argv(settings, models, gpu engine)`
        is the command that starts the worker (in its jail, given the GPU engine when it may use it).
        `cloud`: cloud speech, when chosen in Settings. `load_extra`: test backends (recorded audio)."""
        self._engine = engine
        self._gpu_engine_for = gpu_engine_for
        self._gpu_engine: Path | None = None  # what the running worker's jail was given
        self._cloud = cloud
        self._client = client
        self._downloads: dict[str, dict] = {}  # model id → progress, while (and after) fetching
        self._fetching: asyncio.Task | None = None
        self._mic_level: asyncio.Future | None = None
        self._emit = emit
        self._argv = argv
        self._models = models or models_dir()
        self._load_extra = load_extra or {}
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._settings = VoiceSettings()
        self.state = "off"
        self.note = ""  # why voice is unavailable, or a fallback worth saying
        self._cloud_note = ""  # the note while cloud speech fails and this computer stands in
        self._conversation: str | None = None
        self._last_spoken_at = 0.0
        self._task: str | None = None  # the request being answered out loud
        self._message: str | None = None  # its assistant message streaming now
        self._fed = 0  # characters of that message given to `_sentences`
        self._sentences = Sentences()
        self._follow_up = False
        self._asking: str | None = None  # an approval Mei read out and waits on a spoken answer for
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
        elif self._gpu_engine_for(settings.tts, settings.device) != self._gpu_engine:
            await self.stop()  # the jail itself changes: the GPU joins or leaves it
            await self._spawn()
        elif changed:
            await self._load()

    def needed(self):
        """The local models these settings use: voice detection and Kroko always (Kroko shows what
        is heard live, even when a cloud provider does the final text, and writes it down when the
        cloud can't), and Piper unless Kokoro speaks (it speaks when cloud speech can't)."""
        s = self._settings
        speech = [KOKORO] if s.tts == "kokoro" else [PIPER.get(s.voice, PIPER["amy"])]
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
                                   end_silence_s=s.end_silence_ms / 1000, mic=s.mic, output=s.output,
                                   gpu_engine=str(self._gpu_engine or ""), gpu_idle_s=s.gpu_idle_min * 60,
                                   **self._load_extra))

    async def wait_ready(self, timeout: float = 60.0) -> None:
        await asyncio.wait_for(self._ready.wait(), timeout)

    # ── Models, the microphone, the speakers (setup and Settings) ────────────

    def models(self) -> dict:
        """The models, and with an NVIDIA GPU the GPU engine: never needed, offered when the
        natural voice may use the GPU."""
        needed = {m.folder for m in self.needed()}
        s, gpu = self._settings, gpu_engine.gpu_present()
        rows = [{"id": key, "part": m.part, "size": m.size, "have": have(m, self._models), "needed": m.folder in needed,
                 "offered": False, **self._downloads.get(key, {})} for key, m in CATALOG.items()]
        if gpu:
            rows.append({"id": GPU_ENGINE, "part": gpu_engine.PART, "size": gpu_engine.size(),
                         "have": gpu_engine.installed(gpu_engine.engine_dir()), "needed": False,
                         "offered": s.tts == "kokoro" and s.device != "cpu", **self._downloads.get(GPU_ENGINE, {})})
        return {"state": self.state, "note": self.note, "models": rows, "gpu": gpu,
                "downloading": self._busy(), "voices": voice_choices()}

    def _busy(self) -> bool:
        return self._fetching is not None and not self._fetching.done()

    def download(self, ids: list[str]) -> None:
        """Fetch these models in the background (progress in `models()`), then start voice if it is on."""
        unknown = [i for i in ids if i not in CATALOG and i != GPU_ENGINE]
        if unknown:
            raise ProtocolError("InvalidArgument", f"no voice model {unknown[0]!r}")
        if self._client is None:
            raise ProtocolError("Unavailable", "downloads aren't available here")
        if self._busy():
            raise ProtocolError("Busy", "a download is already running")
        self._fetching = asyncio.ensure_future(self._fetch(ids))

    async def remove(self, ids: list[str]) -> None:
        """Delete downloaded models (or the GPU engine); voice then carries on without them."""
        unknown = [i for i in ids if i not in CATALOG and i != GPU_ENGINE]
        if unknown:
            raise ProtocolError("InvalidArgument", f"no voice model {unknown[0]!r}")
        if self._busy():
            raise ProtocolError("Busy", "a download is running")
        if GPU_ENGINE in ids and self._gpu_engine is not None:
            await self.stop()  # nothing may run from the engine while it is deleted
        for key in ids:
            self._downloads.pop(key, None)
            if key == GPU_ENGINE:
                gpu_engine.remove(gpu_engine.engine_dir())
                continue
            path = self._models / CATALOG[key].folder
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        await self.apply(self._settings)

    async def _fetch(self, ids: list[str]) -> None:
        for key in ids:
            total = gpu_engine.size() if key == GPU_ENGINE else CATALOG[key].size
            progress = self._downloads[key] = {"got": 0, "total": total, "error": ""}

            def report(got: int, total: int, progress: dict = progress) -> None:
                progress.update(got=got, total=total)
            try:
                if key == GPU_ENGINE:
                    await gpu_engine.fetch(self._client, gpu_engine.engine_dir(), report)
                else:
                    await download.fetch(self._client, CATALOG[key], self._models, report)
            except VoiceError as e:
                progress["error"] = e.message
                return
            except Exception as e:  # noqa: BLE001  a disk or network failure: say it, don't crash the runtime
                log.exception("downloading %s failed", key)
                progress["error"] = str(e)[:200]
                return
        await self.apply(self._settings)

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
                if not stopped and (self._follow_up or self._asking):
                    self._follow_up = False  # a follow-up (or the answer to a question) needs no shortcut
                    await self._send(wire.Listen())
                else:
                    self._set("idle")
            case wire.BargeIn():
                self._task = None
            case wire.Woke():
                if time.monotonic() - self._last_spoken_at > FOLLOW_UP_WINDOW_S:
                    self._conversation = None
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
        if self._asking is not None and (CONFIRM.match(text) or DECLINE.match(text)):
            approval, self._asking = self._asking, None
            try:
                self._engine.resolve_approval(ResolveApprovalArgs(
                    command_id=new_id(), approval_id=approval, decision="allow" if CONFIRM.match(text) else "deny",
                    scope="once"), decided_by="voice")
            except ProtocolError as e:  # answered on screen meanwhile, or the action changed
                self._set("idle", e.message)
                return
            self._set("thinking")
            return
        self._asking = None  # anything else: the card stays on screen, and these words join the task
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
            self._ask_aloud(p["approval"])
        elif event.type == "approval.resolved" and p.get("approval_id") == self._asking:
            self._asking = None
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

    def _ask_aloud(self, approval: dict) -> None:
        """Read the action back and listen for "yes, do it", if a voice may approve it (§11.6):
        local, undo recorded, private, nothing sent off this computer, no data lost. Otherwise the
        card on screen is the only way."""
        action = self._engine.store.read_one("SELECT effects FROM actions WHERE id = ?", (approval["action_id"],))
        effects = json.loads(action["effects"] or "{}") if action is not None else {}
        if spoken_ok(effects):
            self._asking = approval["id"]
            ask = [f"I'd like to {speakable_title(approval['card']['title'])}.", "Say yes, do it, or no."]
        else:
            ask = ["I need your OK for that. It's on screen."]
        self._say(self._sentences.flush() + ask)
        asyncio.ensure_future(self._send_quietly(wire.End()))  # this much is said; the task waits

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


def voice_choices() -> dict[str, list[dict]]:
    """Who can speak, per speech choice, by the id the settings keep: Piper's voice, Kokoro's speaker
    number, a cloud provider's voice name ("" for its default)."""
    choices = {"piper": [{"id": key, "label": m.part.removeprefix("voice: ")} for key, m in PIPER.items()],
               "kokoro": [{"id": str(i), "label": kokoro_label(v)} for i, v in enumerate(KOKORO_VOICES)]}
    for key, end in TTS.items():
        choices[key] = [{"id": "", "label": f"{end.voice.capitalize()} (default)"}] + [
            {"id": v, "label": v.capitalize()} for v in end.voices]
    return choices


def spoken_ok(effects: dict) -> bool:
    """May a voice approve an action with these effects? (§11.6: a voice in the room isn't verified.)"""
    return (effects.get("mutates") == "local" and effects.get("undo") == "recorded"
            and effects.get("visibility", "private") == "private" and effects.get("disclosure", "none") != "off_machine"
            and not effects.get("loses_data", False))


def speakable_title(title: str) -> str:
    """A card title as it is said: "Move ~/Music/old.txt to the trash" → "move old.txt in Music to the trash"."""
    def say_path(m: re.Match) -> str:
        return f"{m.group(2)} in {m.group(1)}" if m.group(1) else f"{m.group(2)} in your home folder"
    text = _HOME_PATH.sub(say_path, title)
    return text[:1].lower() + text[1:]
