"""The natural voice (Kokoro) on the GPU, on demand (decision 0019).

Kokoro is the one part of voice the GPU speeds up (spike 0c: first sentence 0.47 s, against 1.37 s
on the CPU). Keeping it there keeps the graphics card awake, so it runs in a process of its own,
started when the person starts talking to Mei (it takes ~1.5–3 s, which their speaking and the
model's thinking usually cover) and ended after some minutes unused, each use restarting the clock.
Ending the process is what lets the card sleep again.

`GpuKokoro` is the worker's speech backend: any sentence due before the GPU is ready, or after it
fails, is said by Kokoro on the CPU, the same voice, so nobody hears the switch. `main` is the GPU
process: it imports the CUDA engine from the downloaded engine folder (on its import path, nowhere
else), and serves one sentence per request over JSON lines on stdin/stdout.
"""

import asyncio
import base64
import contextlib
import os
import sys
from collections.abc import Callable
from pathlib import Path

import msgspec
import numpy as np

from mei.ondemand import OnDemand

from . import gpu_engine
from .parts import Speech, VoiceError

READY_TIMEOUT_S = 60.0
SAY_TIMEOUT_S = 30.0
MAX_LINE = 8 << 20


class _Load(msgspec.Struct, tag="load"):
    models: str
    speaker: int = 0
    speed: float = 1.0


class _Say(msgspec.Struct, tag="say"):
    text: str


class _Ready(msgspec.Struct, tag="ready"):
    pass


class _Failed(msgspec.Struct, tag="failed"):
    message: str


class _Audio(msgspec.Struct, tag="audio"):
    rate: int
    pcm: str  # base64 float32


_requests = msgspec.json.Decoder(_Load | _Say)
_replies = msgspec.json.Decoder(_Ready | _Failed | _Audio)
_encode = msgspec.json.Encoder().encode


class GpuSpeaker:
    """The worker's handle on the GPU process."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc
        self._lock = asyncio.Lock()

    @classmethod
    async def start(cls, engine: Path, load: dict) -> "GpuSpeaker":
        env = {**os.environ, "PYTHONPATH": str(gpu_engine.site(engine)),
               "LD_LIBRARY_PATH": ":".join(gpu_engine.library_dirs(engine))}
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "mei.voice.gpu_speaker", stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env, limit=MAX_LINE)
        speaker = cls(proc)
        try:
            reply = await speaker._ask(_Load(**load), READY_TIMEOUT_S)
        except BaseException:
            await speaker.stop()
            raise
        if not isinstance(reply, _Ready):
            await speaker.stop()
            raise VoiceError("speech", reply.message if isinstance(reply, _Failed) else "the GPU voice answered oddly")
        return speaker

    async def say(self, text: str) -> Speech:
        reply = await self._ask(_Say(text=text), SAY_TIMEOUT_S)
        if isinstance(reply, _Failed):
            raise VoiceError("speech", reply.message)
        if not isinstance(reply, _Audio):
            raise VoiceError("speech", "the GPU voice answered oddly")
        return Speech(np.frombuffer(base64.b64decode(reply.pcm), dtype=np.float32).copy(), reply.rate)

    async def stop(self) -> None:
        proc = self._proc
        if proc.returncode is not None:
            return
        with contextlib.suppress(OSError):
            assert proc.stdin is not None
            proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), 3)
        except TimeoutError:
            proc.kill()
            await proc.wait()

    async def _ask(self, request, timeout: float):
        assert self._proc.stdin is not None and self._proc.stdout is not None
        async with self._lock:
            try:
                self._proc.stdin.write(_encode(request) + b"\n")
                await self._proc.stdin.drain()
                line = await asyncio.wait_for(self._proc.stdout.readline(), timeout)
            except (OSError, TimeoutError) as e:
                raise VoiceError("speech", f"the GPU voice stopped answering ({type(e).__name__})") from None
        if not line:
            raise VoiceError("speech", "the GPU voice stopped")
        try:
            return _replies.decode(line)
        except msgspec.DecodeError:
            raise VoiceError("speech", "the GPU voice answered oddly") from None


class GpuKokoro:
    """Kokoro on the GPU when it's awake, on the CPU otherwise: the same voice either way."""

    name = "kokoro"

    def __init__(self, cpu, engine: Path, load: dict, idle_s: float, note: Callable[[str], None],
                 start=GpuSpeaker.start) -> None:
        self._cpu = cpu
        self._note = note
        self._gpu: OnDemand[GpuSpeaker] = OnDemand("the GPU voice", lambda: start(engine, load), self._stop, idle_s)

    def warm(self) -> None:
        self._gpu.warm()

    async def synthesize(self, text: str) -> Speech:
        gpu = self._gpu.ready
        if gpu is None:
            self._gpu.warm()  # not awake yet: this sentence on the CPU, the next ones likely not
            if self._gpu.error:
                self._note(f"the graphics card didn't start ({self._gpu.error}), so the processor speaks")
            return await self._cpu.synthesize(text)
        try:
            speech = await gpu.say(text)
        except VoiceError as e:
            self._note(f"the graphics card stopped ({e.message}), so the processor speaks")
            await self._gpu.close()
            return await self._cpu.synthesize(text)
        self._gpu.touch()
        return speech

    async def close(self) -> None:
        await self._gpu.close()

    @staticmethod
    async def _stop(speaker: GpuSpeaker) -> None:
        await speaker.stop()


def main() -> None:
    """The GPU process: load Kokoro on CUDA, say it's ready, then speak each sentence asked."""
    from . import local  # here, sherpa-onnx is the CUDA build from the engine folder

    out = sys.stdout.buffer
    tts = None
    for line in sys.stdin.buffer:
        try:
            request = _requests.decode(line)
        except msgspec.DecodeError as e:
            reply: msgspec.Struct = _Failed(message=f"unreadable request: {e}")
        else:
            try:
                if isinstance(request, _Load):
                    engine, device, note = local.kokoro(Path(request.models), request.speaker, request.speed, "gpu")
                    reply = _Ready() if device == "gpu" else _Failed(message=note or "no GPU")
                    tts = engine if device == "gpu" else None
                elif tts is None:
                    reply = _Failed(message="not loaded")
                else:
                    speech = tts.synthesize_now(request.text)
                    reply = _Audio(rate=speech.rate, pcm=base64.b64encode(speech.samples.tobytes()).decode())
            except Exception as e:  # noqa: BLE001  any failure is the worker's to handle: it falls back
                reply = _Failed(message=str(e)[:300] or type(e).__name__)
        out.write(_encode(reply) + b"\n")
        out.flush()


if __name__ == "__main__":
    main()
