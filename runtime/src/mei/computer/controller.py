"""The core's side of computer use (§10, decision 0022): one desktop worker in its jail, behind its own
xdg-dbus-proxy, started on first use. A facade: capabilities ask it to observe and act, and it keeps the
process, the restore token, the control lease and the latest snapshots to itself.
"""

import asyncio
import contextlib
import dataclasses
import itertools
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from mei.ondemand import OnDemand

from . import jail, wire

log = logging.getLogger("mei.computer")

LEASE_EVERY_S = 0.25
LEASE_VALID_MS = 600
READY_TIMEOUT_S = 20
TIMEOUTS_S = {wire.Observe: 25.0, wire.Act: 25.0, wire.OpenSession: 200.0, wire.CloseSession: 5.0}
SOCKET_PATH_MAX = 108  # sun_path
USE_IDLE_S = 30.0  # the Shell's chip and the screen session stay this long after the last look or act
ACTIVE_MS = 1500  # the person used the pointer or keys this recently: they're at the computer
OWN_INPUT_MARGIN_MS = 300  # Mei's own last event, as the Shell's idle clock saw it


class DesktopError(Exception):
    def __init__(self, error: str, message: str) -> None:
        super().__init__(message)
        self.error = error
        self.message = message


class TokenStore(Protocol):
    """Where the portal's restore token lives (the keyring): whoever holds it can start a session
    with no dialog, so it is a secret."""

    async def get(self) -> str: ...
    async def put(self, token: str) -> None: ...


@dataclass
class Seen:
    """A snapshot as the core keeps it: enough to judge an act before it runs (§10.4)."""

    token: str
    window: dict
    app: str
    nodes: dict[str, dict]
    picture: tuple[int, int] | None = None  # its size, when it has one


@dataclass
class _Worker:
    proc: asyncio.subprocess.Process
    proxy: asyncio.subprocess.Process
    ready_fd: int
    socket: Path
    reader: asyncio.Task | None = None
    ready: asyncio.Future = field(default_factory=lambda: asyncio.get_running_loop().create_future())
    pending: dict[int, asyncio.Future] = field(default_factory=dict)


class Desktop:
    def __init__(self, bus_address: str, a11y_address: Callable[[], Awaitable[str]], tokens: TokenStore,
                 runtime_dir: Path, revoked: Callable[[str, bool], None] = lambda _reason, _by_person: None,
                 argv: Callable[[Path, str], list[str]] = jail.worker_argv,
                 overlay: Callable[[bool], Awaitable[None]] | None = None,
                 make_way: Callable[[int], Awaitable[None]] | None = None) -> None:
        """`revoked(reason, by_person)`: the worker stopped input on its own. `by_person`: the kill switch, the
        chip, or the Shell or Mei's extension going away, which end the task; else the lease ran out.
        `overlay(active)`: show or hide the Shell's "using the computer" chip (§10.3). `make_way(window_id)`:
        before injecting input, close Mei's popup (its grab would take the input) and raise the window."""
        self._bus_address = bus_address
        self._a11y_address = a11y_address
        self._tokens = tokens
        self._dir = runtime_dir
        self.revoked = revoked  # settable: the app wires it once the engine exists
        self._argv = argv
        self._ids = itertools.count(1)
        self._worker: _Worker | None = None
        self._starting = asyncio.Lock()
        self._seen: dict[str, Seen] = {}
        self._session_open = False
        self._generation = 0
        self._leasing: asyncio.Task | None = None
        self._overlay = overlay
        self._make_way = make_way
        # A period of use: from the first look or act until USE_IDLE_S after the last. The chip shows
        # for exactly that long, and the screen session closes with it.
        self._use: OnDemand[bool] = OnDemand("computer use", self._begin_use, self._end_use, USE_IDLE_S)
        self._last_input = 0.0  # when Mei last moved the pointer or typed (monotonic)
        self.locked = False
        self.accessibility = False

    # ── What capabilities use ────────────────────────────────────────────────

    async def observe(self, window: dict, monitors: list, *, picture: bool, max_nodes: int = 250) -> dict:
        await self._in_use()
        if picture:
            await self.ensure_session()
        data = await self._request(wire.Observe(id=0, window=window, monitors=monitors, image=picture,
                                                max_nodes=max_nodes))
        self._remember(window, data)
        return data

    async def act(self, token: str, action: str, *, element: str = "", point: list | None = None, text: str = "",
                  window: dict | None = None, monitors: list | None = None, needs_input: bool = True) -> dict:
        await self._in_use()
        if needs_input:
            await self.ensure_session()
            if self._make_way is not None:
                with contextlib.suppress(Exception):  # no Shell to ask: the input goes where it goes
                    await self._make_way(int((window or {}).get("id") or 0))
        before = self._seen.get(token)
        try:
            async with self._lease(needs_input):
                data = await self._request(wire.Act(id=0, token=token, action=action, element=element,
                                                    point=list(point or []), text=text, window=window or {},
                                                    monitors=list(monitors or [])))
        finally:
            if needs_input:
                self._last_input = asyncio.get_running_loop().time()
            self._use.touch()
        self._remember(window or (before.window if before else {}), data)
        return data

    def person_active(self, idle_ms: int) -> bool:
        """Has the person used the pointer or keys lately? The Shell's idle time counts Mei's own input
        too, so it's theirs only when it is shorter than the time since Mei's last event."""
        since_mine_ms = (asyncio.get_running_loop().time() - self._last_input) * 1000
        return idle_ms < ACTIVE_MS and idle_ms + OWN_INPUT_MARGIN_MS < since_mine_ms

    async def set_locked(self, locked: bool) -> None:
        """While the screen is locked nothing is observed or acted on, and the session closes (§10.3)."""
        self.locked = locked
        if locked and self._worker is not None:
            with contextlib.suppress(ConnectionError, RuntimeError):
                self._send(self._worker, wire.Revoke(reason="the screen locked"))
            self._session_open = False
            self._stop_leasing()

    def seen(self, token: str) -> Seen | None:
        """The snapshot, while it is still its window's latest (acting takes a new one)."""
        return self._seen.get(token)

    async def ensure_session(self, *, ask: bool = False) -> None:
        """The RemoteDesktop session, open. Without `ask`, only with the stored restore token: a task never
        shows the portal's dialog; setup does, once."""
        if self._session_open:
            return
        token = await self._tokens.get()
        if not token and not ask:
            raise DesktopError("unavailable", "Mei isn't allowed to use the screen yet: allow it in Mei's setup "
                                              "(Using the computer)")
        data = await self._request(wire.OpenSession(id=0, restore_token=token))
        if data.get("restore_token"):
            await self._tokens.put(str(data["restore_token"]))
        self._session_open = True

    async def allow_screen(self) -> None:
        """Setup's one consent (decision 0022): the portal's dialog, then the session closes again. Its
        restore token is kept, so tasks never see the dialog."""
        self._session_open = False
        await self.ensure_session(ask=True)
        with contextlib.suppress(DesktopError):
            await self._request(wire.CloseSession(id=0))
        self._session_open = False

    async def screen_allowed(self) -> bool:
        return bool(await self._tokens.get())

    async def kill(self, reason: str) -> None:
        """The kill switch's last step (§10.3): stop input and kill the worker, before anything else waits."""
        worker, self._worker = self._worker, None
        self._session_open = False
        self._stop_leasing()
        if worker is not None:
            with contextlib.suppress(ProcessLookupError):
                worker.proc.kill()
        log.info("computer use stopped: %s", reason)
        await self._use.close()
        if worker is not None:
            await self._reap(worker)

    async def stop(self) -> None:
        await self._use.close()
        worker, self._worker = self._worker, None
        self._session_open = False
        self._stop_leasing()
        if worker is None:
            return
        with contextlib.suppress(ConnectionError, RuntimeError):
            self._send(worker, wire.Quit())
        try:
            await asyncio.wait_for(worker.proc.wait(), 5)
        except TimeoutError:
            worker.proc.kill()
        await self._reap(worker)

    # ── A period of use ──────────────────────────────────────────────────────

    async def _in_use(self) -> None:
        if self.locked:
            raise DesktopError("unavailable", "the screen is locked")
        await self._use.get()

    async def _begin_use(self) -> bool:
        if self._overlay is not None:
            with contextlib.suppress(Exception):  # no Shell to show it: computer use still works
                await self._overlay(True)
        return True

    async def _end_use(self, _value: bool) -> None:
        worker = self._worker
        if self._session_open and worker is not None:
            with contextlib.suppress(ConnectionError, RuntimeError, DesktopError):
                await self._request(wire.CloseSession(id=0))
        self._session_open = False
        if self._overlay is not None:
            with contextlib.suppress(Exception):
                await self._overlay(False)

    # ── The control lease (§10.3) ────────────────────────────────────────────

    @contextlib.asynccontextmanager
    async def _lease(self, needed: bool):
        if not needed:
            yield
            return
        self._generation += 1
        generation = self._generation
        worker = await self._started()
        self._send(worker, wire.Lease(generation=generation, valid_ms=LEASE_VALID_MS))
        self._leasing = asyncio.ensure_future(self._renew(worker, generation))
        try:
            yield
        finally:
            self._stop_leasing()
            if self._worker is worker:
                with contextlib.suppress(ConnectionError, RuntimeError):
                    self._send(worker, wire.Lease(generation=generation, valid_ms=0))

    async def _renew(self, worker: _Worker, generation: int) -> None:
        with contextlib.suppress(ConnectionError, RuntimeError):  # the worker stopped: the lease ends with it
            while True:
                await asyncio.sleep(LEASE_EVERY_S)
                self._send(worker, wire.Lease(generation=generation, valid_ms=LEASE_VALID_MS))

    def _stop_leasing(self) -> None:
        if self._leasing is not None:
            self._leasing.cancel()
            self._leasing = None

    # ── The worker ───────────────────────────────────────────────────────────

    async def _request(self, cmd) -> dict:
        worker = await self._started()
        cmd = dataclasses.replace(cmd, id=next(self._ids))
        future = asyncio.get_running_loop().create_future()
        worker.pending[cmd.id] = future
        try:
            self._send(worker, cmd)
            reply: wire.Reply = await asyncio.wait_for(future, TIMEOUTS_S[type(cmd)])
        except TimeoutError:
            raise DesktopError("timeout", "the desktop worker didn't answer in time") from None
        finally:
            worker.pending.pop(cmd.id, None)
        if not reply.ok:
            if reply.error == "revoked":
                self._session_open = False
            raise DesktopError(reply.error or "failed", reply.message or "the desktop worker failed")
        return reply.data

    async def _started(self) -> _Worker:
        async with self._starting:
            if self._worker is not None and self._worker.proc.returncode is None:
                return self._worker
            self._worker = await self._spawn()
            return self._worker

    async def _spawn(self) -> _Worker:
        missing = jail.missing()
        if missing:
            raise DesktopError("unavailable", f"computer use isn't available: {missing}")
        a11y = await self._a11y_address()
        self._dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        socket = self._dir / f"desktop-{os.getpid()}.bus"
        if len(os.fsencode(socket)) >= SOCKET_PATH_MAX:
            raise DesktopError("unavailable", f"the folder for the desktop worker's bus is too deep: {self._dir}")
        socket.unlink(missing_ok=True)
        ready_r, ready_w = os.pipe()
        proxy = await asyncio.create_subprocess_exec(*jail.proxy_argv(self._bus_address, socket, ready_w),
                                                     pass_fds=(ready_w,), stdin=asyncio.subprocess.DEVNULL)
        os.close(ready_w)
        try:
            await asyncio.wait_for(_read_byte(ready_r), 5)
            if not socket.exists():
                raise OSError("no socket")
        except (TimeoutError, OSError):
            os.close(ready_r)
            with contextlib.suppress(ProcessLookupError):
                proxy.kill()
            raise DesktopError("unavailable", "the desktop worker's bus filter didn't start") from None
        proc = await asyncio.create_subprocess_exec(*self._argv(socket, a11y), stdin=asyncio.subprocess.PIPE,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                    limit=wire.MAX_LINE)
        worker = _Worker(proc, proxy, ready_r, socket)
        worker.reader = asyncio.ensure_future(self._read(worker))
        asyncio.ensure_future(self._log_stderr(proc))
        try:
            ready: wire.Ready = await asyncio.wait_for(asyncio.shield(worker.ready), READY_TIMEOUT_S)
        except (TimeoutError, ConnectionError):
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await self._reap(worker)
            raise DesktopError("unavailable", "the desktop worker didn't start (see the Mei log)") from None
        self.accessibility = ready.accessibility
        return worker

    async def _read(self, worker: _Worker) -> None:
        assert worker.proc.stdout is not None
        while line := await worker.proc.stdout.readline():
            try:
                event = wire.event(line)
            except wire.WireError as e:
                log.warning("the desktop worker said something unexpected: %s", e)
                continue
            if isinstance(event, wire.Ready) and not worker.ready.done():
                worker.ready.set_result(event)
            elif isinstance(event, wire.Reply):
                future = worker.pending.get(event.id)
                if future is not None and not future.done():
                    future.set_result(event)
            elif isinstance(event, wire.Revoked):
                self._session_open = False
                self._stop_leasing()
                self.revoked(event.reason, event.by == "shell")
        gone = ConnectionError("the desktop worker stopped")
        if not worker.ready.done():
            worker.ready.set_exception(gone)
        for future in worker.pending.values():
            if not future.done():
                future.set_exception(DesktopError("unavailable", "the desktop worker stopped"))
        if self._worker is worker:
            self._worker = None
            self._session_open = False
            self._stop_leasing()

    def _send(self, worker: _Worker, message) -> None:
        stdin = worker.proc.stdin
        if stdin is None or stdin.is_closing():
            raise ConnectionError("the desktop worker isn't running")
        stdin.write(wire.encode(message))

    async def _reap(self, worker: _Worker) -> None:
        await worker.proc.wait()
        if worker.reader is not None:
            await asyncio.gather(worker.reader, return_exceptions=True)
        with contextlib.suppress(OSError):
            os.close(worker.ready_fd)  # the proxy exits when this closes
        with contextlib.suppress(asyncio.TimeoutError, ProcessLookupError):
            await asyncio.wait_for(worker.proxy.wait(), 3)
        if worker.proxy.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                worker.proxy.kill()
        worker.socket.unlink(missing_ok=True)

    async def _log_stderr(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr is not None
        while line := await proc.stderr.readline():
            text = line.decode("utf-8", "replace").rstrip()
            if not text:
                continue
            # AT-SPI first tries each app's direct socket, which the jail doesn't have, then uses the bus.
            quiet = "Unable to open bus connection" in text
            log.log(logging.DEBUG if quiet else logging.INFO, "desktop worker: %s", text[:500])

    def _remember(self, window: dict, data: dict) -> None:
        token = str(data.get("token") or "")
        if not token:
            return
        nodes = {str(n.get("id")): n for n in data.get("nodes", []) if isinstance(n, dict)}
        picture = data.get("picture")
        size = (int(picture["width"]), int(picture["height"])) if isinstance(picture, dict) else None
        window_id = window.get("id")
        self._seen = {t: s for t, s in self._seen.items() if s.window.get("id") != window_id}
        self._seen[token] = Seen(token, window, str(data.get("app") or ""), nodes, size)


async def _read_byte(fd: int) -> None:
    loop = asyncio.get_running_loop()
    done = loop.create_future()

    def readable() -> None:
        loop.remove_reader(fd)
        try:
            data = os.read(fd, 1)
        except OSError as e:
            done.set_exception(e)
            return
        if data:
            done.set_result(None)
        else:
            done.set_exception(OSError("closed before it was ready"))

    loop.add_reader(fd, readable)
    try:
        await done
    finally:
        loop.remove_reader(fd)
