"""Something costly kept only while it is used: the GPU for a voice today, a local model tomorrow.
It starts on first use (or when warmed ahead of use), stays while used, and stops after `idle_s`
without use; every use restarts that clock. A start that fails is reported to whoever waits on it
and can be tried again later; nothing here retries on its own.
"""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

T = TypeVar("T")
log = logging.getLogger("mei.ondemand")


class OnDemand(Generic[T]):
    def __init__(self, name: str, start: Callable[[], Awaitable[T]], stop: Callable[[T], Awaitable[None]],
                 idle_s: float) -> None:
        self.name = name
        self.idle_s = idle_s
        self.error = ""  # why the last start failed, until one succeeds
        self._start = start
        self._stop = stop
        self._starting: asyncio.Task[T] | None = None
        self._value: T | None = None
        self._idle: asyncio.TimerHandle | None = None
        self._stopping: asyncio.Task[None] | None = None

    @property
    def ready(self) -> T | None:
        """The resource if it is up, without waiting or starting it."""
        return self._value

    def warm(self) -> None:
        """Start it now, ahead of use, without waiting."""
        if self._value is None and self._starting is None:
            self._begin()

    async def get(self) -> T:
        """The resource, started if need be; counts as a use."""
        if self._value is None:
            if self._starting is None:
                self._begin()
            assert self._starting is not None
            await asyncio.shield(self._starting)
        assert self._value is not None
        self.touch()
        return self._value

    def touch(self) -> None:
        """A use: the idle clock starts again."""
        if self._value is None:
            return
        if self._idle is not None:
            self._idle.cancel()
        self._idle = asyncio.get_running_loop().call_later(self.idle_s, self._expire)

    async def close(self) -> None:
        """Stop it now (shutting down, or settings changed)."""
        if self._starting is not None:
            self._starting.cancel()
            with contextlib.suppress(BaseException):
                await self._starting
        if self._stopping is not None:
            await self._stopping
        await self._release()

    def _begin(self) -> None:
        self._starting = asyncio.ensure_future(self._run_start())
        # A warm-up nobody waits on may fail: its error is in `error`, not an unretrieved exception.
        self._starting.add_done_callback(lambda t: t.cancelled() or t.exception())

    async def _run_start(self) -> T:
        if self._stopping is not None:  # a stop still in progress finishes first
            await self._stopping
        try:
            value = await self._start()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # reported to whoever waits; the next use tries again
            self.error = getattr(e, "message", "") or str(e) or type(e).__name__
            log.warning("%s didn't start: %s", self.name, self.error)
            raise
        finally:
            self._starting = None
        self._value, self.error = value, ""
        self.touch()
        log.info("%s is up", self.name)
        return value

    def _expire(self) -> None:
        self._idle = None
        if self._value is not None and self._stopping is None:
            self._stopping = asyncio.ensure_future(self._expired())

    async def _expired(self) -> None:
        try:
            await self._release()
            log.info("%s stopped after %.0f s unused", self.name, self.idle_s)
        finally:
            self._stopping = None

    async def _release(self) -> None:
        value, self._value = self._value, None
        if self._idle is not None:
            self._idle.cancel()
            self._idle = None
        if value is not None:
            try:
                await self._stop(value)
            except Exception:  # noqa: BLE001  stopping must not take the caller down with it
                log.exception("stopping %s failed", self.name)
