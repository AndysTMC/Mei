"""Composition root: wires the store, providers, engine, and D-Bus service, and runs until stopped."""

import asyncio
import logging
import os
import signal
from pathlib import Path

import httpx
from dbus_fast import BusType
from dbus_fast.aio import MessageBus

from mei.core.engine import Engine
from mei.ipc import dbus_patch
from mei.ipc.service import RuntimeService
from mei.protocol import ProviderConfig
from mei.providers.base import Provider, ProviderError
from mei.providers.fake import FakeProvider
from mei.providers.openai_chat import OpenAIChatProvider
from mei.secrets import KeyringLocked, KeyringUnavailable, lookup_provider_key
from mei.store.db import Store

log = logging.getLogger("mei.app")

EXIT_LOCKED = 75  # EX_TEMPFAIL: another instance owns the data directory


def data_dir() -> Path:
    if os.environ.get("MEI_DATA_DIR"):
        return Path(os.environ["MEI_DATA_DIR"])
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "mei"


def provider_factory(bus: MessageBus, client: httpx.AsyncClient):
    async def make(cfg: ProviderConfig) -> Provider:
        if cfg.kind == "fake":
            return FakeProvider({**cfg.options, "model": cfg.model or "fake-1"})
        if cfg.kind == "openai_chat":
            label = cfg.label or cfg.id or "Provider"
            key = ""
            if cfg.id:
                try:
                    key = await lookup_provider_key(bus, cfg.id) or ""
                except KeyringLocked:
                    raise ProviderError(f"{label}: the keyring is locked. Unlock it, then try again.") from None
                except KeyringUnavailable as e:
                    log.warning("keyring unavailable: %s", e)
            return OpenAIChatProvider(client, label=label, url=cfg.url, model=cfg.model,
                                      api_key=key, headers=cfg.headers)
        raise ProviderError("No model provider is configured.")

    return make


async def serve() -> int:
    dbus_patch.apply()
    store = Store(data_dir())
    bus = await MessageBus(bus_type=BusType.SESSION, negotiate_unix_fd=True).connect()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        loop.add_signal_handler(sig, stop.set)
    async with httpx.AsyncClient(http2=False, follow_redirects=False) as client:
        engine = Engine(store, publisher=None, provider_factory=provider_factory(bus, client))
        service = RuntimeService(bus, engine)
        engine.publisher = service  # the service needs the engine and the engine publishes through it
        engine.recover()
        await service.start()
        disconnected = asyncio.ensure_future(bus.wait_for_disconnect())
        stopped = asyncio.ensure_future(stop.wait())
        done, _ = await asyncio.wait({disconnected, stopped}, return_when=asyncio.FIRST_COMPLETED)
        await engine.shutdown()
        if disconnected in done:
            disconnected.exception()  # retrieve it (EOFError from dbus-fast) so asyncio doesn't warn
            log.error("lost the session bus; exiting so systemd can restart the runtime")
            store.close()
            return 1
        stopped.result()
        bus.disconnect()
    store.close()
    log.info("stopped")
    return 0
