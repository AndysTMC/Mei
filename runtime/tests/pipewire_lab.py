"""A private PipeWire for voice tests (decision 0024): its own daemon and WirePlumber on their own
socket, with null devices only. Nothing plays aloud, no real microphone opens, and the person's
PipeWire is never reached: clients get only this lab's socket.

- `lab.speaker`: where Mei plays (a null sink, also the clock).
- `lab.mic`: the microphone Mei records (a virtual source).
- the room: what the speaker plays, back into the microphone through a synthetic room's impulse
  response (direct sound, early reflections, a reverberant tail) at a chosen level;
- `lab.talker`: the person, whose voice goes straight into the microphone.
- the probe: one recorder with three channels, so the microphone, the talker, and the speaker
  are sample-aligned. Talker onset → the speaker going silent is barge-in's real latency.

Not collected by pytest (no test_ prefix); used by test_voice_echo.py and voice_bench.py.
"""

import contextlib
import os
import shutil
import subprocess
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

SPEAKER, MIC, TALKER = "lab.speaker", "lab.mic", "lab.talker"
RATE = 48000
PROBE_RATE = 16000
CONFIG_NAME = "mei-lab.conf"  # how a client can tell it reached the lab, not the person's PipeWire

DAEMON = f"""
context.properties = {{
    core.daemon = true
    core.name = pipewire-0
    link.max-buffers = 16
    default.clock.rate = {RATE}
    default.clock.allowed-rates = [ {RATE} ]
}}
context.spa-libs = {{
    audio.convert.* = audioconvert/libspa-audioconvert
    audio.adapt     = audioconvert/libspa-audioconvert
    support.*       = support/libspa-support
}}
context.modules = [
    {{ name = libpipewire-module-protocol-native }}
    {{ name = libpipewire-module-metadata }}
    {{ name = libpipewire-module-spa-node-factory }}
    {{ name = libpipewire-module-client-node }}
    {{ name = libpipewire-module-access }}
    {{ name = libpipewire-module-adapter }}
    {{ name = libpipewire-module-link-factory }}
]
context.objects = [
    {{ factory = metadata args = {{ metadata.name = default }} }}
    {{ factory = adapter args = {{ factory.name = support.null-audio-sink node.name = {SPEAKER}
        node.description = "Lab speaker" media.class = Audio/Sink audio.position = [ MONO ] audio.rate = {RATE}
        priority.session = 1000 node.driver = true priority.driver = 20000 object.linger = true }} }}
    {{ factory = adapter args = {{ factory.name = support.null-audio-sink node.name = {TALKER}
        node.description = "Lab talker" media.class = Audio/Sink audio.position = [ MONO ] audio.rate = {RATE}
        priority.session = 10 object.linger = true }} }}
    {{ factory = adapter args = {{ factory.name = support.null-audio-sink node.name = {MIC}
        node.description = "Lab mic" media.class = Audio/Source/Virtual audio.position = [ MONO ] audio.rate = {RATE}
        priority.session = 2000 object.linger = true }} }}
]
"""

# WirePlumber's policy and nothing else: no ALSA, Bluetooth or cameras, no D-Bus, no saved state.
WIREPLUMBER = """
wireplumber.profiles = {
  mei-lab = {
    inherits = [ policy, mixin.systemwide-session, mixin.stateless ]
    check.no-media-session = disabled
    support.snapd-permission-prompting = disabled
  }
}
"""

ROOM = """
context.properties = {{ log.level = 1 }}
context.spa-libs = {{ audio.convert.* = audioconvert/libspa-audioconvert support.* = support/libspa-support }}
context.modules = [
  {{ name = libpipewire-module-protocol-native }}
  {{ name = libpipewire-module-client-node }}
  {{ name = libpipewire-module-adapter }}
  {{ name = libpipewire-module-filter-chain
    args = {{
      node.description = "Lab room"
      audio.rate = {rate}
      audio.channels = 1
      audio.position = [ MONO ]
      filter.graph = {{
        nodes = [ {{ type = builtin name = room label = convolver config = {{ filename = "{ir}" gain = {gain} }} }} ]
      }}
      capture.props = {{ node.name = lab.room.in stream.capture.sink = true target.object = {speaker} node.passive = false }}
      playback.props = {{ node.name = lab.room.out node.autoconnect = false }}
    }}
  }}
]
"""


def missing() -> str:
    """Why the lab can't run here, or ""."""
    for tool in ("pipewire", "wireplumber", "pw-cat", "pw-record", "pw-link", "pw-cli"):
        if shutil.which(tool, path="/usr/bin:/bin") is None:
            return f"{tool} isn't installed"
    from mei.voice.pipewire import echo_canceller_missing
    return echo_canceller_missing()


def room_response(rt60: float, drr_db: float, seed: int = 1) -> np.ndarray:
    """A room's impulse response at RATE, with unit energy: direct sound at 1.5 ms and two early
    reflections, `drr_db` louder than a diffuse tail that falls 60 dB in `rt60` seconds. A laptop
    on a desk, its speakers centimetres from its microphone, is about +6 dB; a speaker across a
    lively room, −6 dB or less."""
    rng = np.random.default_rng(seed)
    n = int(RATE * max(0.05, 1.5 * rt60))
    t = np.arange(n) / RATE
    tail = rng.standard_normal(n) * np.exp(-6.9 * t / max(rt60, 1e-3))
    tail[: int(0.004 * RATE)] = 0
    direct = np.zeros(n)
    direct[int(0.0015 * RATE)], direct[int(0.006 * RATE)], direct[int(0.011 * RATE)] = 1.0, 0.4, -0.25
    tail *= np.sqrt(np.sum(direct ** 2) / np.sum(tail ** 2) / 10 ** (drr_db / 10))
    ir = direct + tail
    return ir / np.sqrt(np.sum(ir ** 2))


class Lab:
    def __init__(self) -> None:
        # Short: a socket path must fit in 108 bytes.
        self.root = Path(tempfile.mkdtemp(prefix="mei-pw-", dir="/tmp"))
        self.runtime = self.root / "r"
        for d in ("r", "config/wireplumber/wireplumber.conf.d", "state", "home"):
            (self.root / d).mkdir(parents=True)
        self.runtime.chmod(0o700)
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.root / "home"), "XDG_RUNTIME_DIR": str(self.runtime),
                    "XDG_CONFIG_HOME": str(self.root / "config"), "XDG_STATE_HOME": str(self.root / "state"),
                    "LANG": "C.UTF-8"}
        self._procs: list[subprocess.Popen] = []
        self._room: subprocess.Popen | None = None

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        (self.root / CONFIG_NAME).write_text(DAEMON)
        (self.root / "config/wireplumber/wireplumber.conf.d/lab.conf").write_text(WIREPLUMBER)
        self._spawn("pipewire", "-c", str(self.root / CONFIG_NAME), log="daemon.log")
        self._until(lambda: (self.runtime / "pipewire-0").exists(), "the lab's PipeWire didn't start")
        self._spawn("wireplumber", "-p", "mei-lab", log="wireplumber.log")
        self._until(lambda: "WirePlumber" in self.run("pw-cli", "ls", "Client"), "the lab's WirePlumber didn't start")
        self.link(f"{TALKER}:monitor_MONO", f"{MIC}:input_MONO")

    def stop(self) -> None:
        for proc in reversed(self._procs):
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            proc.wait()
        self._procs.clear()
        shutil.rmtree(self.root, ignore_errors=True)

    def __enter__(self) -> "Lab":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()

    def is_mine(self, env: dict | None = None) -> bool:
        """Does `env` (default: this process's) reach this lab's PipeWire? Checked before anything
        could play or record, so a mistake can't reach the person's speakers or microphone."""
        info = subprocess.run(["pw-cli", "info", "0"], env=dict(os.environ) if env is None else env,
                              capture_output=True, text=True, timeout=5).stdout
        return f'core.name = "pipewire-0"' in info and CONFIG_NAME in info and str(self.runtime) in (
            (env or os.environ).get("XDG_RUNTIME_DIR", ""))

    @contextlib.contextmanager
    def environ(self):
        """This process's environment pointed at the lab (for a worker run in-process)."""
        saved = dict(os.environ)
        for key in ("PIPEWIRE_REMOTE", "PIPEWIRE_RUNTIME_DIR", "PIPEWIRE_CORE", "PULSE_SERVER", "PULSE_RUNTIME_PATH"):
            os.environ.pop(key, None)
        os.environ["XDG_RUNTIME_DIR"] = str(self.runtime)
        try:
            if not self.is_mine():
                raise RuntimeError("the environment doesn't reach the lab's PipeWire")
            yield
        finally:
            os.environ.clear()
            os.environ.update(saved)

    # ── The room and the person ──────────────────────────────────────────────

    def room(self, echo_gain: float, rt60: float = 0.4, drr_db: float = 6.0) -> None:
        """Carry what the speaker plays into the microphone at `echo_gain` (energy gain of the
        room's response: 0.5 puts Mei's voice into the microphone 6 dB below its playback level),
        through `room_response(rt60, drr_db)`. The default is a laptop on a desk."""
        if self._room is not None:
            with contextlib.suppress(ProcessLookupError):
                self._room.kill()
            self._room.wait()
            self._procs.remove(self._room)
        ir = room_response(rt60, drr_db) * echo_gain
        peak = max(1.0, float(np.max(np.abs(ir))))
        path = self.root / f"room-{rt60}-{drr_db}.wav"
        with wave.open(str(path), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes((ir / peak * 32767).astype(np.int16).tobytes())
        conf = self.root / "room.conf"
        conf.write_text(ROOM.format(rate=RATE, ir=path, gain=peak, speaker=SPEAKER))
        self._room = self._spawn("pipewire", "-c", str(conf), log="room.log")
        self.link("lab.room.out:output_MONO", f"{MIC}:input_MONO")

    def talk(self, samples: np.ndarray, rate: int, gain: float = 0.5) -> subprocess.Popen:
        """The person says `samples` (into the microphone, not through the room). From a file, so
        nothing blocks the caller (a worker may share its event loop)."""
        path = self.root / f"said-{time.monotonic_ns()}.f32"
        (np.asarray(samples, np.float32) * gain).tofile(path)
        proc = subprocess.Popen(["pw-cat", "--playback", "--raw", "--format", "f32", "--rate", str(rate), "--channels", "1",
                                 "--latency", "20ms", "--target", TALKER, str(path)], env=self.env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._procs.append(proc)
        return proc

    # ── Recording what happened ──────────────────────────────────────────────

    @contextlib.contextmanager
    def probe(self):
        """Record the microphone, the talker, and the speaker, sample-aligned, while the block
        runs; yields a dict that gets "mic", "talker", "speaker" (float32 at PROBE_RATE)."""
        path = self.root / f"probe-{time.monotonic_ns()}.f32"
        proc = subprocess.Popen(["pw-record", "--raw", "--format", "f32", "--rate", str(PROBE_RATE), "--channels", "3",
                                 "--channel-map", "FL,FR,FC", "--latency", "20ms",
                                 "-P", "{ node.name = lab.probe node.autoconnect = false }", str(path)],
                                env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        got: dict[str, np.ndarray] = {}
        try:
            for port, channel in ((f"{MIC}:capture_MONO", "FL"), (f"{TALKER}:monitor_MONO", "FR"),
                                  (f"{SPEAKER}:monitor_MONO", "FC")):
                self.link(port, f"lab.probe:input_{channel}")
            yield got
        finally:
            proc.terminate()
            proc.wait(5)
        audio = np.fromfile(path, np.float32)
        audio = audio[: len(audio) // 3 * 3].reshape(-1, 3)
        got.update(mic=audio[:, 0].copy(), talker=audio[:, 1].copy(), speaker=audio[:, 2].copy())
        path.unlink()

    # ── Plumbing ─────────────────────────────────────────────────────────────

    def run(self, *argv: str) -> str:
        return subprocess.run(list(argv), env=self.env, capture_output=True, text=True, timeout=5).stdout

    def link(self, out: str, into: str) -> None:
        """Link two ports once both exist (the room and the probe link by hand, not by policy)."""
        self._until(lambda: out in self.run("pw-link", "-o") and into in self.run("pw-link", "-i"),
                    f"no ports {out} → {into}")
        subprocess.run(["pw-link", out, into], env=self.env, check=True, capture_output=True, timeout=5)

    def _spawn(self, *argv: str, log: str) -> subprocess.Popen:
        with open(self.root / log, "ab") as out:
            proc = subprocess.Popen(list(argv), env=self.env, stdin=subprocess.DEVNULL, stdout=out, stderr=out)
        self._procs.append(proc)
        return proc

    @staticmethod
    def _until(ready, failure: str, timeout: float = 5.0) -> None:
        end = time.monotonic() + timeout
        while not ready():
            if time.monotonic() > end:
                raise TimeoutError(failure)
            time.sleep(0.02)


# ── Reading a probe ──────────────────────────────────────────────────────────

def onset(audio: np.ndarray, threshold: float, after_s: float = 0.0) -> float | None:
    """Seconds into `audio` where it first exceeds `threshold` (after `after_s`)."""
    loud = np.flatnonzero(np.abs(audio[int(after_s * PROBE_RATE):]) > threshold)
    return after_s + loud[0] / PROBE_RATE if len(loud) else None


def silent_from(audio: np.ndarray) -> float | None:
    """Seconds into `audio` after which nothing more plays (a null sink is exactly silent)."""
    sound = np.flatnonzero(np.abs(audio) > 1e-6)
    return (sound[-1] + 1) / PROBE_RATE if len(sound) else None


def level_db(audio: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.square(audio, dtype=np.float64))) + 1e-9))
