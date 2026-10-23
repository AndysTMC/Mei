"""Echo cancellation for barge-in (decision 0024).

With stand-ins for PipeWire's programs: the canceller's configuration, its failures (it exits, or
gives no audio), and that the worker then falls back to the plain microphone, saying so.

In a private PipeWire with null devices (pipewire_lab.py): the real worker, in its real jail with
only that PipeWire's socket, hears Mei's own reply come back from the speaker through a simulated
laptop on a desk, at speaker-like level. With the canceller it doesn't stop itself; without it, it
does; and a person talking over it still stops it, and is heard. Not within §4's 350 ms: through
the canceller it takes ~0.37 s at the median and up to ~0.75 s (decision 0024; voice_bench.py
--only echo measures it). Nothing plays aloud and no real microphone opens. Skipped where
PipeWire's echo canceller or the voice models aren't installed.
"""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

sherpa = pytest.importorskip("sherpa_onnx")

import pipewire_lab  # noqa: E402
from mei.voice import jail, local, pipewire, wire  # noqa: E402
from mei.voice import worker as worker_module  # noqa: E402
from mei.voice.models import KROKO, PIPER, SILERO, have  # noqa: E402
from mei.voice.pipewire import EchoCancelledSource, canceller_config  # noqa: E402
from mei.voice.worker import Worker  # noqa: E402

SPIKE_MODELS = Path.home() / ".cache/mei-spikes/0c/models"
REPLY = ("Here is a long answer about the weather this week. It will be mostly sunny, with a little rain on "
         "Thursday evening.")
TALKER_GAIN = 0.5  # the person's voice at the microphone about as loud as Mei's echo there (both ≈ −27 dBFS)
ECHO_GAIN = 0.5  # Mei's voice back into the microphone 6 dB below its playback level
# §4's target is 0.35 s; through the canceller the lab measured up to ~0.75 s (decision 0024).
# This bound catches it getting worse, or the person not being heard at all.
BARGE_IN_LIMIT_S = 1.0


@pytest.fixture(scope="module")
def models() -> Path:
    root = Path(os.environ.get("MEI_VOICE_MODELS") or SPIKE_MODELS)
    if not all(have(m, root) for m in (SILERO, KROKO, PIPER["amy"])):
        pytest.skip("voice models not downloaded")
    return root


def fake(tmp_path: Path, name: str, body: str) -> str:
    path = tmp_path / name
    path.write_text(f"#!{sys.executable}\nimport sys, time\n{body}\n")
    path.chmod(0o755)
    return str(path)


SILENCE_FOREVER = "while True:\n    sys.stdout.buffer.write(bytes(6400)); sys.stdout.flush(); time.sleep(0.1)"


# ── The canceller, with stand-ins ────────────────────────────────────────────

def test_the_canceller_is_private_follows_the_chosen_devices_and_runs_at_48_khz():
    conf = canceller_config("mei.echo-cancel.x", mic="alsa_input.usb-Brio", output="alsa_output.pci-analog")
    assert "monitor.mode = true" in conf  # Mei's speech goes straight to the speakers
    assert "audio.rate = 48000" in conf  # ~11 dB of cancellation at 16 kHz, 30–68 dB at 48 kHz
    assert 'node.name = "mei.echo-cancel.x.source"' in conf and "priority.session = 0" in conf
    assert 'target.object = "alsa_input.usb-Brio"' in conf and 'target.object = "alsa_output.pci-analog"' in conf
    assert "webrtc.gain_control = false" in conf and "webrtc.noise_suppression = false" in conf
    assert "target.object" not in canceller_config("mei.echo-cancel.x")  # the defaults, followed as they change


def test_a_device_name_cannot_add_to_the_canceller_configuration():
    conf = canceller_config("n", mic='x" } ] context.modules = [ { name = libpipewire-module-protocol-pulse } ] #')
    assert 'target.object = "x\\" } ] context.modules' in conf  # one quoted string, quotes escaped
    with pytest.raises(pipewire.VoiceError):
        canceller_config("n", mic="x\ncontext.modules = []")


async def test_a_canceller_that_exits_ends_the_recording_and_says_why(tmp_path, monkeypatch):
    monkeypatch.setattr(pipewire, "PIPEWIRE", fake(tmp_path, "pipewire", "print('E mod.echo-cancel: aec plugin "
                                                   "not available', file=sys.stderr); time.sleep(0.3); sys.exit(1)"))
    monkeypatch.setattr(pipewire, "PW_RECORD", fake(tmp_path, "pw-record", SILENCE_FOREVER))
    source = EchoCancelledSource(workdir=tmp_path)
    await source.start()
    async with asyncio.timeout(5):
        async for _chunk in source.chunks():
            pass
    assert "aec plugin not available" in source.failure
    await source.stop()
    assert not list(tmp_path.glob("mei.echo-cancel.*.conf"))


async def test_a_canceller_that_gives_no_audio_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(pipewire, "PIPEWIRE", fake(tmp_path, "pipewire", "time.sleep(60)"))
    monkeypatch.setattr(pipewire, "PW_RECORD", fake(tmp_path, "pw-record", "time.sleep(60)"))
    monkeypatch.setattr(pipewire, "FIRST_AUDIO_S", 0.3)
    source = EchoCancelledSource(workdir=tmp_path)
    await source.start()
    assert [c async for c in source.chunks()] == [] and source.failure == "the echo canceller gave no audio"
    await source.stop()


async def test_stopping_ends_both_processes_and_records_only_the_cancellers_source(tmp_path, monkeypatch):
    args = tmp_path / "args"
    monkeypatch.setattr(pipewire, "PIPEWIRE", fake(tmp_path, "pipewire", "time.sleep(60)"))
    monkeypatch.setattr(pipewire, "PW_RECORD", fake(tmp_path, "pw-record", f"open({str(args)!r}, 'w').write("
                                                    f"repr(sys.argv))\n{SILENCE_FOREVER}"))
    source = EchoCancelledSource(mic="lab.mic", workdir=tmp_path)
    await source.start()
    async for _chunk in source.chunks():
        break
    canceller, recorder = source._proc, source._recorder._proc
    await source.stop()
    assert canceller.returncode is not None and recorder.returncode is not None and not source.open
    argv = eval(args.read_text())  # noqa: S307  our own stand-in wrote it
    assert argv[argv.index("--target") + 1].endswith(".source") and "node.dont-fallback = true" in argv[argv.index("-P") + 1]


def test_the_canceller_ends_when_the_worker_does(tmp_path):
    """A `pipewire -c` client outlives its server; it must not outlive its worker."""
    pid_file = tmp_path / "pid"
    script = (f"import asyncio, sys\nfrom mei.voice import pipewire\npipewire.PIPEWIRE = {fake(tmp_path, 'pipewire', 'time.sleep(60)')!r}\n"
              f"pipewire.PW_RECORD = {fake(tmp_path, 'pw-record', 'time.sleep(60)')!r}\n"
              "async def main():\n    s = pipewire.EchoCancelledSource(workdir=__import__('pathlib').Path(sys.argv[1]))\n"
              "    await s.start()\n    open(sys.argv[2], 'w').write(str(s._proc.pid))\n    await asyncio.sleep(60)\n"
              "asyncio.run(main())\n")
    worker = subprocess.Popen([sys.executable, "-c", script, str(tmp_path), str(pid_file)])
    try:
        for _ in range(100):
            if pid_file.exists() and pid_file.read_text():
                break
            time.sleep(0.05)
        canceller = int(pid_file.read_text())
        worker.kill()
        worker.wait()
        for _ in range(50):
            if not Path(f"/proc/{canceller}").exists() or "Z" in Path(f"/proc/{canceller}/stat").read_text().split()[2]:
                break
            time.sleep(0.05)
        else:
            os.kill(canceller, 9)
            pytest.fail("the canceller outlived its worker")
    finally:
        worker.kill()


# ── Speakers or earphones: the output's route, from pw-dump ──────────────────

def laptop(route: str, port: str, default: str = "alsa_output.pci.analog-stereo") -> list[dict]:
    """The shape pw-dump gives a laptop's sound card: the sink, its device's active route, and the
    default sink in the "default" metadata (from this machine, trimmed)."""
    return [
        {"id": 53, "type": "PipeWire:Interface:Device", "info": {
            "props": {"device.name": "alsa_card.pci"}, "params": {"Route": [
                {"index": 0, "direction": "Input", "name": "analog-input-internal-mic", "devices": [0],
                 "info": [2, "port.type", "mic", "port.availability-group", "Legacy 1"]},
                {"index": 1, "direction": "Output", "name": route, "devices": [3],
                 "info": [2, "port.type", port, "port.availability-group", "Legacy 2"]}]}}},
        {"id": 62, "type": "PipeWire:Interface:Node", "info": {"props": {
            "node.name": "alsa_output.pci.analog-stereo", "media.class": "Audio/Sink", "device.id": 53,
            "card.profile.device": 3}}},
        {"id": 70, "type": "PipeWire:Interface:Node", "info": {"props": {
            "node.name": "bluez_output.earbuds", "media.class": "Audio/Sink", "device.id": 71}}},
        {"id": 71, "type": "PipeWire:Interface:Device", "info": {"props": {"device.form-factor": "headset"}}},
        {"id": 40, "type": "PipeWire:Interface:Metadata", "props": {"metadata.name": "default"}, "metadata": [
            {"subject": 0, "key": "default.audio.sink", "type": "Spa:String:JSON", "value": {"name": default}}]},
    ]


def test_earphones_are_told_from_speakers_by_the_route_or_the_device():
    assert pipewire.into_ears(laptop("analog-output-headphones", "headphones"))  # the default sink
    assert not pipewire.into_ears(laptop("analog-output-speaker", "speaker"))
    assert pipewire.into_ears(laptop("analog-output-speaker", "speaker"), "bluez_output.earbuds")
    assert pipewire.into_ears(laptop("analog-output-speaker", "speaker", default="bluez_output.earbuds"))
    assert not pipewire.into_ears(laptop("analog-output-headphones", "headphones"), "lab.speaker")  # unknown: speakers
    assert not pipewire.into_ears([]) and not pipewire.into_ears([None, 3, {"type": "PipeWire:Interface:Node"}])


async def test_with_earphones_the_watch_hears_the_plain_microphone(tmp_path, models, monkeypatch):
    """Nothing to cancel: the canceller isn't started, and talking over Mei is as fast as without it."""
    monkeypatch.setattr(worker_module, "output_into_ears", into_earphones)
    monkeypatch.setattr(pipewire, "PIPEWIRE", fake(tmp_path, "pipewire", "open(sys.argv[0] + '.ran', 'w')"))
    events = Events()
    w = Worker(out=events)
    mic, played = tmp_path / "mic.f32", tmp_path / "played.f32"
    np.zeros(16000 * 20, np.float32).tofile(mic)
    await w.handle(wire.Load(models=str(models), source_file=str(mic), sink_file=str(played), barge_in=True))
    await events.until(wire.Ready)
    w._barge_source = EchoCancelledSource(workdir=tmp_path)
    await w.handle(wire.Say(text="Short."))
    await w.handle(wire.End())
    await events.until(wire.Spoken)
    assert not (tmp_path / "pipewire.ran").exists() and not events.of(wire.Failed)
    await w.handle(wire.Quit())


# ── The worker's choice, and its fallback ────────────────────────────────────

class Events:
    def __init__(self) -> None:
        self.got: list[tuple[float, wire.Event]] = []
        self._changed = asyncio.Event()

    def write(self, data: bytes) -> None:
        now = asyncio.get_running_loop().time()
        self.got.extend((now, wire.event(line)) for line in data.splitlines())
        self._changed.set()

    def flush(self) -> None:
        pass

    def of(self, kind) -> list:
        return [e for _at, e in self.got if isinstance(e, kind)]

    async def until(self, kind, timeout: float = 30.0):
        async with asyncio.timeout(timeout):
            while True:
                if found := self.of(kind):
                    return found[0]
                self._changed.clear()
                await self._changed.wait()


@pytest.mark.parametrize(("barge_in", "echo_cancel", "missing", "cancels"), [
    (True, True, "", True), (True, False, "", False), (False, True, "", False),
    (True, True, "PipeWire's echo-cancel module isn't installed", False)])
async def test_the_watch_hears_through_the_canceller_only_when_it_is_wanted_and_there(
        models, monkeypatch, barge_in, echo_cancel, missing, cancels):
    monkeypatch.setattr(worker_module, "echo_canceller_missing", lambda: missing)
    events = Events()
    w = Worker(out=events)
    await w.handle(wire.Load(models=str(models), barge_in=barge_in, echo_cancel=echo_cancel))  # opens nothing
    ready = await events.until(wire.Ready)
    assert ready.echo_cancel is cancels and isinstance(w._barge_source, EchoCancelledSource) is cancels
    if missing:
        assert ready.note == f"{missing}, so talking over Mei works with earphones only"
    await w.handle(wire.Quit())


async def through_speakers(_output: str = "") -> bool:
    return False


async def into_earphones(_output: str = "") -> bool:
    return True


async def test_when_the_canceller_fails_mei_keeps_talking_and_falls_back_saying_so(tmp_path, models, monkeypatch):
    monkeypatch.setattr(worker_module, "output_into_ears", through_speakers)  # not this computer's route
    monkeypatch.setattr(pipewire, "PIPEWIRE", fake(tmp_path, "pipewire", "print('E echo-cancel: gone', "
                                                   "file=sys.stderr); sys.exit(1)"))
    monkeypatch.setattr(pipewire, "PW_RECORD", fake(tmp_path, "pw-record", "time.sleep(60)"))
    events = Events()
    w = Worker(out=events)
    mic, played = tmp_path / "mic.f32", tmp_path / "played.f32"
    np.zeros(16000 * 20, np.float32).tofile(mic)
    await w.handle(wire.Load(models=str(models), source_file=str(mic), sink_file=str(played), barge_in=True))
    await events.until(wire.Ready)
    w._barge_source = EchoCancelledSource(workdir=tmp_path)  # recorded audio has no canceller of its own
    await w.handle(wire.Say(text="This answer is long enough to still be playing when the canceller fails."))
    await w.handle(wire.End())
    failed = await events.until(wire.Failed)
    assert failed.part == "echo cancellation" and failed.message.endswith("works with earphones only")
    assert "gone" in failed.message and w._barge_source is w._source
    spoken = await events.until(wire.Spoken)
    assert not spoken.stopped and not events.of(wire.BargeIn)
    await w.handle(wire.Quit())


# ── In a private PipeWire, the real worker in its real jail ─────────────────

@pytest.fixture(scope="module")
def lab():
    if why := pipewire_lab.missing():
        pytest.skip(f"no private PipeWire for the echo tests: {why}")
    with pipewire_lab.Lab() as lab:
        lab.room(ECHO_GAIN)  # a laptop on a desk
        yield lab


@pytest.fixture(scope="module")
def piper(models):
    return local.piper(models, "amy")


class Jailed:
    """The worker in its jail, given only the lab's PipeWire socket."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self.proc = proc
        self.events = Events()
        self._reader = asyncio.ensure_future(self._read())

    @classmethod
    async def start(cls, lab, models: Path, monkeypatch) -> "Jailed":
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(lab.runtime))
        argv = jail.worker_argv(models)
        socket = argv.index("--bind-try") + 1
        assert argv[socket] == f"{lab.runtime}/pipewire-0" and lab.is_mine({"XDG_RUNTIME_DIR": str(lab.runtime),
                                                                              "PATH": "/usr/bin:/bin"})
        proc = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL, limit=wire.MAX_LINE)
        return cls(proc)

    async def _read(self) -> None:
        while line := await self.proc.stdout.readline():
            self.events.write(line)

    async def send(self, *cmds: wire.Command) -> None:
        for cmd in cmds:
            self.proc.stdin.write(wire.encode(cmd))
        await self.proc.stdin.drain()

    async def load(self, models: Path, **load) -> wire.Ready:
        self.events.got.clear()
        await self.send(wire.Load(models=str(models), mic=pipewire_lab.MIC, output=pipewire_lab.SPEAKER,
                                  barge_in=True, **load))
        return await self.events.until(wire.Ready, 60)

    async def close(self) -> None:
        await self.send(wire.Quit())
        self.proc.stdin.close()
        await asyncio.wait_for(self.proc.wait(), 20)
        await self._reader


@pytest.fixture
async def jailed(lab, models, monkeypatch):
    if not jail.available():
        pytest.skip("needs bubblewrap")
    worker = await Jailed.start(lab, models, monkeypatch)
    yield worker
    await worker.close()


async def test_in_its_jail_mei_does_not_hear_itself_through_the_speakers(lab, models, jailed):
    ready = await jailed.load(models, echo_cancel=True)
    assert ready.echo_cancel, ready  # the canceller needs nothing of the jail but PipeWire's socket
    with lab.probe() as heard:
        await jailed.send(wire.Say(text=REPLY), wire.End())
        spoken = await jailed.events.until(wire.Spoken, 60)
    assert not spoken.stopped and not jailed.events.of(wire.BargeIn) and not jailed.events.of(wire.Failed)
    played = pipewire_lab.silent_from(heard["speaker"])
    assert played > 5.0 and pipewire_lab.level_db(heard["mic"]) > -35  # all of it, and loud at the microphone


async def test_without_the_canceller_the_same_echo_stops_mei(lab, models, jailed):
    ready = await jailed.load(models, echo_cancel=False)
    assert not ready.echo_cancel
    await jailed.send(wire.Say(text=REPLY), wire.End())
    await jailed.events.until(wire.BargeIn, 30)  # the echo is loud enough to matter


async def test_talking_over_mei_through_the_canceller_stops_it_and_is_heard(lab, models, jailed, piper):
    ready = await jailed.load(models, echo_cancel=True)
    assert ready.echo_cancel
    said = await piper.synthesize("Pause the music please.")
    with lab.probe() as heard:
        await jailed.send(wire.Say(text=REPLY), wire.End())
        await jailed.events.until(wire.Speaking, 30)
        await asyncio.sleep(1.5)  # well past the grace window, and the canceller's start
        lab.talk(said.samples, said.rate, TALKER_GAIN)
        await jailed.events.until(wire.BargeIn, 10)
        final = await jailed.events.until(wire.Final, 30)
    began = pipewire_lab.onset(heard["talker"], 0.02 * TALKER_GAIN)
    stopped = pipewire_lab.silent_from(heard["speaker"])
    assert began is not None and stopped - began < BARGE_IN_LIMIT_S, (began, stopped)
    assert "music" in final.text.lower()  # what was said over the echo is still heard
