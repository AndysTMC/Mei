"""Audio through PipeWire's own clients, `pw-record` and `pw-cat` (decision 0017): they need only
the `pipewire-0` socket, which is all the voice worker's jail has. PortAudio's PulseAudio path
would need the PulseAudio socket, whose protocol lets a client load server modules.

Echo cancellation (decision 0024) is PipeWire's own too: its echo-cancel module, run by `pipewire`
as a client of the same socket, only while the barge-in watch has the microphone.
"""

import asyncio
import collections
import contextlib
import ctypes
import glob
import json
import os
import secrets
import signal
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np

from .parts import CHUNK, SAMPLE_RATE, Speech, VoiceError

PW_RECORD = "/usr/bin/pw-record"
PW_CAT = "/usr/bin/pw-cat"
PIPEWIRE = "/usr/bin/pipewire"
PW_DUMP = "/usr/bin/pw-dump"
LATENCY = "20ms"  # small, so barge-in silences speech quickly
# Where distributions keep PipeWire's modules and SPA plugins (lib/<triplet>, lib64, lib).
LIB_DIRS = ("/usr/lib/*", "/usr/lib64", "/usr/lib")
# The canceller's first audio arrives ~0.15 s after it starts (lab, three runs); none after this
# long means it isn't working (its microphone missing, say), and the watch says so.
FIRST_AUDIO_S = 2.0
# Mei's recorders are named so, so the core can tell other apps' recording from Mei's own
# (mic_users.py; the canceller's nodes start with "mei." too).
RECORDER_NAME = "mei.microphone"
# Recording only from the canceller's source: wait for it to appear, and never record the plain
# microphone in its place (WirePlumber would otherwise fall back to the default source).
WAIT_FOR_TARGET = "node.dont-fallback = true node.linger = true"
CANCELLER_NODES = "mei.echo-cancel."  # its nodes' names start so; desktop/sound.py leaves them out of Settings
# Outputs into the person's ears, not the room: nothing to cancel, and a canceller with no echo to
# learn from holds the person's voice down for about a second (lab, decision 0024).
EAR_PORTS = {"headphones", "headset", "earpiece", "handset"}  # a route's port.type
EAR_FORMS = {"headphone", "headset", "hands-free", "handset"}  # device.form-factor


class PipeWireSource:
    """The default microphone (or `target`, a PipeWire node name). `wait`: only `target`, waiting
    for it to appear."""

    def __init__(self, target: str = "", wait: bool = False) -> None:
        self._target = target
        self._wait = wait
        self._proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if self._proc is not None:
            return
        argv = [PW_RECORD, "--raw", "--format", "f32", "--rate", str(SAMPLE_RATE), "--channels", "1",
                "--latency", LATENCY, *(["--target", self._target] if self._target else []),
                "-P", f"{{ node.name = {RECORDER_NAME} {WAIT_FOR_TARGET if self._wait else ''} }}", "-"]
        try:
            self._proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.DEVNULL,
                                                              stdout=asyncio.subprocess.PIPE,
                                                              stderr=asyncio.subprocess.DEVNULL)
        except OSError as e:
            raise VoiceError("microphone", f"couldn't start pw-record: {e.strerror}") from None

    async def chunks(self, samples: int = CHUNK) -> AsyncIterator[np.ndarray]:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        want = samples * 4
        while True:
            try:
                data = await proc.stdout.readexactly(want)
            except asyncio.IncompleteReadError:
                if self._proc is not proc:
                    return  # stopped
                # It ended by itself: the microphone or PipeWire went away. Silence would be a lie.
                self._proc = None
                code = await proc.wait()
                raise VoiceError("microphone", f"recording stopped (pw-record exit {code}); "
                                               "check that a microphone is connected") from None
            yield np.frombuffer(data, dtype=np.float32).copy()

    async def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            await _end(proc)


class PipeWireSink:
    """Speech out through one `pw-cat` stream per run of speech at one sample rate."""

    def __init__(self, target: str = "") -> None:
        self._target = target
        self._proc: asyncio.subprocess.Process | None = None
        self._rate = 0

    async def play(self, speech: Speech) -> None:
        if self._proc is None or self._rate != speech.rate:
            await self.drain()
            self._proc = await self._open(speech.rate)
            self._rate = speech.rate
        proc = self._proc
        assert proc.stdin is not None
        try:
            proc.stdin.write(np.asarray(speech.samples, dtype=np.float32).tobytes())
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            if self._proc is not proc:
                return  # stopped meanwhile
            self._proc = None
            raise VoiceError("speaker", f"playing stopped (pw-cat exit {await proc.wait()}); "
                                        "check the sound output") from None

    async def drain(self) -> None:
        """Wait until everything queued has been played, then close the stream."""
        proc, self._proc = self._proc, None
        if proc is None:
            return
        if proc.stdin is not None:
            proc.stdin.close()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                await proc.stdin.wait_closed()
        if code := await proc.wait():
            raise VoiceError("speaker", f"playing failed (pw-cat exit {code}); check the sound output")

    async def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            await _end(proc)  # what is already in the graph (one quantum, ~20 ms) still plays

    async def _open(self, rate: int) -> asyncio.subprocess.Process:
        argv = [PW_CAT, "--playback", "--raw", "--format", "f32", "--rate", str(rate), "--channels", "1",
                "--latency", LATENCY, "--media-role", "Assistant",
                *(["--target", self._target] if self._target else []), "-"]
        try:
            return await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE,
                                                        stdout=asyncio.subprocess.DEVNULL,
                                                        stderr=asyncio.subprocess.DEVNULL)
        except OSError as e:
            raise VoiceError("speaker", f"couldn't start pw-cat: {e.strerror}") from None


async def output_into_ears(output: str = "") -> bool:
    """Does `output` ("" for the default) play into earphones or a headset right now? Asked of
    PipeWire with `pw-dump` (~30 ms, opens no audio). False when it can't tell."""
    try:
        proc = await asyncio.create_subprocess_exec(PW_DUMP, stdin=asyncio.subprocess.DEVNULL,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    except OSError:
        return False
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), 2.0)
        dump = json.loads(out)
        return isinstance(dump, list) and into_ears(dump, output)
    except (TimeoutError, ValueError, AttributeError, TypeError):  # slow, or not the shape pw-dump gives
        return False
    finally:
        if proc.returncode is None:
            await _end(proc)


def into_ears(dump: list, output: str = "") -> bool:
    """Does `output` ("" for the default sink) play into the person's ears, by its device's form
    factor or its active route (a laptop's jack switches the route to Headphones)? Anything
    unknown counts as speakers."""
    dump = [o for o in dump if isinstance(o, dict)]
    if not output:
        defaults = (o for o in dump if o.get("type", "").endswith("Metadata")
                    and (o.get("props") or {}).get("metadata.name") == "default")
        output = next((m["value"].get("name", "") for d in defaults for m in d.get("metadata") or []
                       if m.get("key") == "default.audio.sink" and isinstance(m.get("value"), dict)), "")
    nodes = {o.get("id"): (o.get("info") or {}) for o in dump if o.get("type", "").endswith("Node")}
    sink = next((info for info in nodes.values() if (info.get("props") or {}).get("node.name") == output), None)
    if sink is None:
        return False
    props = sink.get("props") or {}
    device = next((o.get("info") or {} for o in dump if o.get("type", "").endswith("Device")
                   and o.get("id") == props.get("device.id")), {})
    if (props.get("device.form-factor") or (device.get("props") or {}).get("device.form-factor")) in EAR_FORMS:
        return True
    for route in (device.get("params") or {}).get("Route") or []:
        if route.get("direction") == "Output" and props.get("card.profile.device") in (route.get("devices") or []):
            info = route.get("info") or []
            pairs = dict(zip(info[1::2], info[2::2]))  # [count, key, value, key, value, …]
            return pairs.get("port.type") in EAR_PORTS
    return False


def echo_canceller_missing() -> str:
    """Why PipeWire's echo canceller can't run here, or "" if it can."""
    if not os.access(PIPEWIRE, os.X_OK):
        return "PipeWire's own program isn't installed"
    if not any(glob.glob(f"{d}/pipewire-0.3/libpipewire-module-echo-cancel.so") for d in LIB_DIRS):
        return "PipeWire's echo-cancel module isn't installed"
    if not any(glob.glob(f"{d}/spa-0.2/aec/libspa-aec-webrtc.so") for d in LIB_DIRS):
        return "PipeWire's WebRTC echo canceller isn't installed"
    return ""


def canceller_config(name: str, mic: str = "", output: str = "") -> str:
    """`pipewire -c` configuration for a private echo canceller named `name`: it records `mic` (""
    for the default), takes what `output` plays (its monitor) as the echo to remove, and offers the
    result as `<name>.source`. Monitor mode, so Mei's speech goes straight to the speakers, not
    through the canceller, and other sounds playing are removed too. At 48 kHz: at 16 kHz the module
    removed only ~11 dB of a simulated room's echo, at 48 kHz 30–68 dB (decision 0024). The
    module's streams are passive, so the microphone runs only while Mei records the source. Its
    own gain control and noise suppression are off: what Mei hears changes only by the echo."""
    capture = f"target.object = {_spa(mic)}" if mic else ""
    reference = f"target.object = {_spa(output)}" if output else ""
    return f"""context.properties = {{ application.name = "Mei" log.level = 1 }}
context.spa-libs = {{ audio.convert.* = audioconvert/libspa-audioconvert support.* = support/libspa-support }}
context.modules = [
    {{ name = libpipewire-module-protocol-native }}
    {{ name = libpipewire-module-client-node }}
    {{ name = libpipewire-module-adapter }}
    {{ name = libpipewire-module-echo-cancel
        args = {{
            library.name = aec/libspa-aec-webrtc
            monitor.mode = true
            audio.rate = 48000
            audio.channels = 1
            audio.position = [ MONO ]
            aec.args = {{ webrtc.gain_control = false webrtc.noise_suppression = false }}
            capture.props = {{ node.name = {_spa(name + ".capture")} node.description = "Mei" {capture} }}
            sink.props = {{ node.name = {_spa(name + ".reference")} node.description = "Mei" {reference} }}
            source.props = {{ node.name = {_spa(name + ".source")} node.description = "Mei (echo cancelled)"
                              priority.session = 0 }}
        }}
    }}
]
"""


def _spa(text: str) -> str:
    """A quoted string for a PipeWire configuration (device names come from Settings)."""
    if any(c in text for c in "\0\n\r"):
        raise VoiceError("echo cancellation", "a device name can't contain line breaks")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class EchoCancelledSource:
    """The microphone with what the speakers play taken out (decision 0024): PipeWire's WebRTC echo
    canceller, run as a private `pipewire -c` client only between `start` and `stop`, with Mei
    recording its source. Nothing in the person's PipeWire setup changes; when it stops, its nodes
    are gone. It lives only while the microphone is open, because GNOME shows the microphone in use
    while any recording stream exists, running or not. The worker uses it only while Mei plays
    through speakers (`into_ears`).

    `failure` says why it stopped giving audio on its own (it exited, or never gave any)."""

    def __init__(self, mic: str = "", output: str = "", workdir: Path = Path("/tmp")) -> None:
        self._name = f"{CANCELLER_NODES}{secrets.token_hex(4)}"
        self._config = workdir / f"{self._name}.conf"
        self._mic, self._output = mic, output
        self._recorder = PipeWireSource(f"{self._name}.source", wait=True)
        self._proc: asyncio.subprocess.Process | None = None
        self._watchdog: asyncio.Task | None = None
        self.failure = ""

    @property
    def open(self) -> bool:
        return self._proc is not None

    async def start(self) -> None:
        if self._proc is not None:
            return
        self.failure = ""
        self._config.write_text(canceller_config(self._name, self._mic, self._output))
        try:
            self._proc = await asyncio.create_subprocess_exec(PIPEWIRE, "-c", str(self._config),
                                                              stdin=asyncio.subprocess.DEVNULL,
                                                              stdout=asyncio.subprocess.DEVNULL,
                                                              stderr=asyncio.subprocess.PIPE,
                                                              preexec_fn=_die_with_parent)
        except OSError as e:
            raise VoiceError("echo cancellation", f"couldn't start PipeWire: {e.strerror}") from None
        self._watchdog = asyncio.ensure_future(self._watch(self._proc))
        await self._recorder.start()

    async def chunks(self, samples: int = CHUNK) -> AsyncIterator[np.ndarray]:
        audio = aiter(self._recorder.chunks(samples))
        try:
            first = await asyncio.wait_for(anext(audio), FIRST_AUDIO_S)
        except StopAsyncIteration:
            return
        except TimeoutError:
            self.failure = self.failure or "the echo canceller gave no audio"
            return
        yield first
        async for chunk in audio:
            yield chunk

    async def stop(self) -> None:
        proc, self._proc = self._proc, None
        watchdog, self._watchdog = self._watchdog, None
        await self._recorder.stop()
        if proc is not None:
            await _end(proc)
        if watchdog is not None:
            await asyncio.gather(watchdog, return_exceptions=True)
        self._config.unlink(missing_ok=True)

    async def _watch(self, proc: asyncio.subprocess.Process) -> None:
        """Keep the canceller's last words; if it ends on its own, end the recording too."""
        assert proc.stderr is not None
        last: collections.deque[str] = collections.deque(maxlen=2)
        while line := await proc.stderr.readline():
            last.append(line.decode("utf-8", "replace").strip()[:200])
        await proc.wait()
        if self._proc is proc:
            code = proc.returncode or 0
            why = "; ".join(last) or (f"signal {-code}" if code < 0 else f"exit {code}")
            self.failure = f"the echo canceller stopped ({why})"
            await self._recorder.stop()


def _die_with_parent() -> None:
    """In the canceller, before it starts: end when the worker does. A `pipewire -c` client stays
    on even after losing its server, so a worker that died would otherwise leave it behind (the
    worker's jail does this too, but tests and the bench run the worker outside it)."""
    ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG


async def _end(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    await proc.wait()
