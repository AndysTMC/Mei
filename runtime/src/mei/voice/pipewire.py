"""Audio through PipeWire's own clients, `pw-record` and `pw-cat` (decision 0017): they need only
the `pipewire-0` socket, which is all the voice worker's jail has. PortAudio's PulseAudio path
would need the PulseAudio socket, whose protocol lets a client load server modules.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

import numpy as np

from .parts import SAMPLE_RATE, Speech, VoiceError

PW_RECORD = "/usr/bin/pw-record"
PW_CAT = "/usr/bin/pw-cat"
CHUNK_SAMPLES = SAMPLE_RATE // 10  # 100 ms
LATENCY = "20ms"  # small, so barge-in silences speech quickly


class PipeWireSource:
    """The default microphone (or `target`, a PipeWire node name)."""

    def __init__(self, target: str = "") -> None:
        self._target = target
        self._proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        if self._proc is not None:
            return
        argv = [PW_RECORD, "--raw", "--format", "f32", "--rate", str(SAMPLE_RATE), "--channels", "1",
                "--latency", LATENCY, *(["--target", self._target] if self._target else []), "-"]
        try:
            self._proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.DEVNULL,
                                                              stdout=asyncio.subprocess.PIPE,
                                                              stderr=asyncio.subprocess.DEVNULL)
        except OSError as e:
            raise VoiceError("microphone", f"couldn't start pw-record: {e.strerror}") from None

    async def chunks(self) -> AsyncIterator[np.ndarray]:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        want = CHUNK_SAMPLES * 4
        while True:
            try:
                data = await proc.stdout.readexactly(want)
            except asyncio.IncompleteReadError:
                return  # stopped
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
        assert self._proc.stdin is not None
        self._proc.stdin.write(np.asarray(speech.samples, dtype=np.float32).tobytes())
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            await self._proc.stdin.drain()

    async def drain(self) -> None:
        """Wait until everything queued has been played, then close the stream."""
        proc, self._proc = self._proc, None
        if proc is None:
            return
        if proc.stdin is not None:
            proc.stdin.close()
            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
                await proc.stdin.wait_closed()
        await proc.wait()

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


async def _end(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    await proc.wait()
