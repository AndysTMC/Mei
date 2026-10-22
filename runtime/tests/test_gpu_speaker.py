"""The natural voice on the GPU, on demand (decision 0019): the GPU is woken when listening starts,
the CPU (same voice) says whatever is due before it's awake or after it fails, and it's let go
after the idle time. The real GPU process runs only where its engine is installed."""

import asyncio
import os
from pathlib import Path

import numpy as np
import pytest

from mei.voice import gpu_engine, jail
from mei.voice.gpu_speaker import GpuKokoro, GpuSpeaker
from mei.voice.parts import Speech, VoiceError


class Cpu:
    name = "kokoro"

    def __init__(self) -> None:
        self.said: list[str] = []

    def warm(self) -> None:
        pass

    async def synthesize(self, text: str) -> Speech:
        self.said.append(text)
        return Speech(np.zeros(10, np.float32), 24000)


class FakeGpu:
    def __init__(self, fail_say: bool = False) -> None:
        self.said: list[str] = []
        self.stopped = False
        self._fail = fail_say

    async def say(self, text: str) -> Speech:
        if self._fail:
            raise VoiceError("speech", "CUDA error")
        self.said.append(text)
        return Speech(np.ones(10, np.float32), 24000)

    async def stop(self) -> None:
        self.stopped = True


def voice(start_s=0.2, idle_s=5.0, fail_start=False, fail_say=False):
    cpu, notes, gpus = Cpu(), [], []

    async def start(engine, load):
        await asyncio.sleep(start_s)
        if fail_start:
            raise VoiceError("speech", "no CUDA device")
        gpus.append(FakeGpu(fail_say))
        return gpus[-1]
    return GpuKokoro(cpu, Path("/engine"), {}, idle_s, notes.append, start=start), cpu, gpus, notes


async def test_the_cpu_speaks_until_the_gpu_is_awake_then_the_gpu_does():
    tts, cpu, gpus, notes = voice(start_s=0.2)
    tts.warm()  # listening started
    first = await tts.synthesize("It will be sunny.")  # due before the GPU is up
    await asyncio.sleep(0.3)
    second = await tts.synthesize("Around eighteen degrees.")
    assert cpu.said == ["It will be sunny."] and gpus[0].said == ["Around eighteen degrees."]
    assert first.samples[0] == 0 and second.samples[0] == 1 and notes == []
    await tts.close()
    assert gpus[0].stopped


async def test_the_gpu_is_let_go_after_the_idle_time_and_woken_again():
    tts, _, gpus, _ = voice(start_s=0.05, idle_s=0.3)
    tts.warm()
    await asyncio.sleep(0.1)
    await tts.synthesize("One.")
    await asyncio.sleep(0.5)
    assert gpus[0].stopped  # unused for longer than the idle time
    tts.warm()
    await asyncio.sleep(0.1)
    await tts.synthesize("Two.")
    assert len(gpus) == 2 and gpus[1].said == ["Two."]
    await tts.close()


async def test_a_gpu_that_wont_start_or_fails_leaves_the_cpu_speaking_and_says_why():
    tts, cpu, _, notes = voice(start_s=0.01, fail_start=True)
    tts.warm()
    await asyncio.sleep(0.05)
    await tts.synthesize("Hello.")
    assert cpu.said == ["Hello."] and "didn't start (no CUDA device)" in notes[0]
    tts, cpu, gpus, notes = voice(start_s=0.01, fail_say=True)
    tts.warm()
    await asyncio.sleep(0.05)
    await tts.synthesize("Hello.")
    assert cpu.said == ["Hello."] and "stopped (CUDA error)" in notes[0] and gpus[0].stopped


def test_the_jail_gets_the_gpu_and_the_engine_only_when_given_them(tmp_path):
    plain = jail.worker_argv(tmp_path)
    assert "--dev-bind" not in plain
    with_gpu = jail.worker_argv(tmp_path, gpu_engine=tmp_path / "engine")
    ro = [with_gpu[i + 1] for i, a in enumerate(with_gpu) if a == "--ro-bind"]
    assert str(tmp_path / "engine") in ro
    if os.path.exists("/dev/nvidiactl"):
        assert with_gpu[with_gpu.index("--dev-bind") + 1].startswith("/dev/nvidia")


ENGINE = Path(os.environ.get("MEI_GPU_ENGINE", "/nonexistent"))
MODELS = Path(os.environ.get("MEI_VOICE_MODELS") or Path.home() / ".cache/mei-spikes/0c/models")


@pytest.mark.skipif(not (gpu_engine.gpu_present() and gpu_engine.installed(ENGINE)
                         and (MODELS / "kokoro-en-v0_19").is_dir()), reason="needs an NVIDIA GPU and the GPU engine")
async def test_the_real_gpu_process_speaks_and_frees_the_gpu_when_stopped():
    speaker = await GpuSpeaker.start(ENGINE, {"models": str(MODELS), "speaker": 0, "speed": 1.0})
    speech = await speaker.say("Dark mode is on.")
    assert speech.rate == 24000 and speech.seconds > 0.5
    await speaker.stop()
    assert speaker._proc.returncode is not None  # the process (and its hold on the GPU) is gone


def gpu_processes() -> list[str]:
    import subprocess
    out = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader"],
                         capture_output=True, text=True, timeout=20).stdout
    return [line for line in out.splitlines() if line.strip()]


@pytest.mark.skipif(not (gpu_engine.gpu_present() and gpu_engine.installed(ENGINE) and jail.available()
                         and (MODELS / "kokoro-en-v0_19").is_dir()), reason="needs an NVIDIA GPU, the GPU engine, bwrap")
async def test_in_its_jail_the_worker_wakes_the_gpu_to_speak_then_lets_it_go(tmp_path):
    from mei.voice import wire
    mic, out = tmp_path / "mic.f32", tmp_path / "out"
    out.mkdir()
    np.zeros(16000, np.float32).tofile(mic)
    before = gpu_processes()
    proc = await asyncio.create_subprocess_exec(
        *jail.worker_argv(MODELS, gpu_engine=ENGINE, readable=(mic,), writable=(out,)),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, limit=wire.MAX_LINE)
    events: list[wire.Event] = []

    async def until(kind, timeout=60.0):
        async with asyncio.timeout(timeout):
            while not any(isinstance(e, kind) for e in events):
                events.append(wire.event(await proc.stdout.readline()))

    def send(cmd):
        proc.stdin.write(wire.encode(cmd))
    send(wire.Load(models=str(MODELS), tts="kokoro", gpu_engine=str(ENGINE), gpu_idle_s=2.0,
                   source_file=str(mic), source_realtime=False, sink_file=str(out / "played.f32")))
    await until(wire.Ready)
    assert next(e for e in events if isinstance(e, wire.Ready)).device == "gpu"
    send(wire.Listen())  # listening wakes the GPU
    await until(wire.NoSpeech)
    woke = asyncio.get_running_loop().time()
    async with asyncio.timeout(15):
        while len(gpu_processes()) <= len(before):
            await asyncio.sleep(0.25)
    assert asyncio.get_running_loop().time() - woke < 5  # awake within the time a person speaks
    send(wire.Say(text="Dark mode is on."))
    send(wire.End())
    await until(wire.Spoken)
    assert not any(isinstance(e, wire.Failed) for e in events), events
    await asyncio.sleep(4)  # idle for longer than gpu_idle_s: let go
    assert len(gpu_processes()) == len(before)
    send(wire.Quit())
    await proc.wait()
