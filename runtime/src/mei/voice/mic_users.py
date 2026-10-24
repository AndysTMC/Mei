"""Which other apps are recording (decision 0025): "Hey Mei" pauses while one is, so a call or a
recording app has the microphone to itself, and GNOME's microphone indicator shows only that app.

Read from PipeWire's graph with `pw-dump --monitor`, which opens no audio and reports each change as
it happens, rather than by polling the whole graph. Runs in the core (not the worker's jail) and
only while the wake word is armed. No voice engine needed: no numpy here.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable

log = logging.getLogger("mei.voice")
PW_DUMP = "/usr/bin/pw-dump"
ARGV = (PW_DUMP, "--monitor", "--no-colors")
RESTARTS = (1.0, 5.0, 30.0)  # back-off when pw-dump stops; after these, give up and say so
STEADY_S = 60.0  # pw-dump that ran this long starts a new run of back-offs
# Level meters that show as recording (the Shell skips these too), and Mei's own nodes.
NOT_RECORDING = {"org.gnome.VolumeControl", "org.PulseAudio.pavucontrol"}
MEI_NODES = "mei."


def records_mic(props: dict) -> bool:
    """Is this node another app recording a microphone? Not Mei's own (its recorders and echo
    canceller are named "mei.…"), not a capture of what the speakers play, not a level meter."""
    name = str(props.get("node.name") or "")
    return (props.get("media.class") == "Stream/Input/Audio" and not name.startswith(MEI_NODES)
            and not _true(props.get("stream.capture.sink")) and not _true(props.get("stream.monitor"))
            and props.get("application.id") not in NOT_RECORDING)


def _true(value) -> bool:
    return value is True or value == "true"


class Recorders:
    """The graph's recording streams, from pw-dump's batches: each a JSON array of objects, an
    object whose "info" is null having gone."""

    def __init__(self) -> None:
        self._nodes: dict[int, bool] = {}  # node id → another app recording

    def update(self, batch: list) -> None:
        for obj in batch:
            if not isinstance(obj, dict) or not isinstance(obj.get("id"), int):
                continue
            info = obj.get("info")
            if info is None:
                self._nodes.pop(obj["id"], None)
            elif obj.get("type") == "PipeWire:Interface:Node" and isinstance(info, dict) and "props" in info:
                self._nodes[obj["id"]] = records_mic(info.get("props") or {})

    @property
    def others(self) -> bool:
        return any(self._nodes.values())


class MicUsers:
    """Watches whether another app is recording; `on_change(others)` on each change, and
    `on_trouble(message)` while it can't tell ("" once it can again)."""

    def __init__(self, on_change: Callable[[bool], None], on_trouble: Callable[[str], None],
                 argv: tuple[str, ...] = ARGV) -> None:
        self._on_change = on_change
        self._on_trouble = on_trouble
        self._argv = argv
        self._task: asyncio.Task | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._known = asyncio.Event()  # the graph has been read at least once, or can't be
        self.others = False

    @property
    def running(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        if self._task is None:
            self._known.clear()
            self._task = asyncio.ensure_future(self._run())

    async def known(self, timeout: float = 1.0) -> None:
        """Wait (briefly) until `others` reflects the graph, if watching."""
        if self._task is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._known.wait(), timeout)

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._set(False)

    async def _run(self) -> None:
        failures = 0
        while True:
            began = asyncio.get_running_loop().time()
            try:
                await self._watch()
                if asyncio.get_running_loop().time() - began >= STEADY_S:
                    failures = 0  # it worked for a while: a new run of back-offs
                why = "pw-dump stopped"
            except OSError as e:
                why = f"couldn't start pw-dump: {e.strerror}"
            self._set(False)  # can't tell: don't hold the wake word off on stale news
            self._known.set()
            if failures >= len(RESTARTS):
                self._on_trouble(f"can't tell whether another app is recording ({why})")
                log.warning("voice: gave up watching for other apps recording: %s", why)
                return
            delay = RESTARTS[failures]
            failures += 1
            self._on_trouble(f"can't tell whether another app is recording ({why}); trying again in {delay:.0f} s")
            await asyncio.sleep(delay)

    async def _watch(self) -> None:
        """Follow pw-dump until it ends."""
        self._proc = proc = await asyncio.create_subprocess_exec(
            *self._argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=16 << 20)
        assert proc.stdout is not None
        recorders, lines, first = Recorders(), [], True
        try:
            while line := await proc.stdout.readline():
                text = line.decode("utf-8", "replace").rstrip("\n")
                lines.append(text)
                if text not in ("]", "[]"):  # a batch ends with a line holding only "]" (or is "[]")
                    continue
                try:
                    batch = json.loads("\n".join(lines))
                except ValueError:
                    log.warning("voice: pw-dump gave something unexpected")
                    batch = []
                lines = []
                recorders.update(batch if isinstance(batch, list) else [])
                if first:
                    first = False
                    self._on_trouble("")
                self._set(recorders.others)
                self._known.set()
        finally:
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
            await proc.wait()

    def _set(self, others: bool) -> None:
        if others != self.others:
            self.others = others
            self._on_change(others)
