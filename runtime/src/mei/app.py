"""Composition root: wires the store, providers, engine, and D-Bus service, and runs until stopped."""

import asyncio
import logging
import os
import signal
from pathlib import Path

import httpx
from dbus_fast import BusType
from dbus_fast.aio import MessageBus

from mei import legacy
from mei.core.engine import Engine
from mei.ipc import dbus_patch
from mei.ipc.service import RUNTIME_VERSION, RuntimeService
from mei.protocol import ProviderConfig
from mei.providers import factory, models
from mei.providers.base import Provider, ProviderError
from mei.providers.profiles import PROFILES
from mei.secrets import KeyringLocked, KeyringUnavailable, lookup_provider_key, store_provider_key
from mei.store.db import Store

log = logging.getLogger("mei.app")

EXIT_LOCKED = 75  # EX_TEMPFAIL: another instance owns the data directory
USER_AGENT = f"Mei/{RUNTIME_VERSION} (+https://github.com/AndysTMC/Mei)"


def data_dir() -> Path:
    if os.environ.get("MEI_DATA_DIR"):
        return Path(os.environ["MEI_DATA_DIR"])
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return Path(base) / "mei"


def key_lookup(bus: MessageBus):
    async def key_for(provider_id: str) -> str:
        label = PROFILES[provider_id].label if provider_id in PROFILES else provider_id
        try:
            return await lookup_provider_key(bus, provider_id) or ""
        except KeyringLocked:
            raise ProviderError(f"{label}: the keyring is locked. Unlock it, then try again.") from None
        except KeyringUnavailable as e:
            log.warning("keyring unavailable: %s", e)
            return ""

    return key_for


def provider_factory(client: httpx.AsyncClient, key_for):
    async def make(cfg: ProviderConfig) -> Provider:
        return await factory.build(cfg, client, key_for)

    return make


def model_lister(client: httpx.AsyncClient, key_for):
    async def list_for(provider_id: str, url: str) -> dict:
        try:
            result = await models.list_models(client, provider_id, url=url, api_key=await key_for(provider_id))
        except ProviderError as e:
            return {"models": [], "requires_key": False, "from_fallback": False, "error": str(e)}
        return {"models": result.models, "requires_key": result.requires_key, "from_fallback": result.from_fallback}

    return list_for


async def import_legacy(store: Store, bus: MessageBus) -> None:
    keyring = legacy.Keyring(store=lambda pid, key: store_provider_key(bus, pid, key),
                             lookup=lambda pid: lookup_provider_key(bus, pid))
    report, _events = await legacy.run(store, data_dir(), legacy.DconfCli(), keyring)
    if report.settings_imported or report.conversations or report.keys_moved or report.keys_pending:
        log.info("imported earlier settings: providers=%s keys_moved=%s keys_pending=%s conversations=%d messages=%d",
                 report.providers, report.keys_moved, report.keys_pending, report.conversations, report.messages)


async def serve() -> int:
    dbus_patch.apply()
    store = Store(data_dir())
    bus = await MessageBus(bus_type=BusType.SESSION, negotiate_unix_fd=True).connect()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        loop.add_signal_handler(sig, stop.set)
    if legacy.enabled(data_dir_overridden="MEI_DATA_DIR" in os.environ):
        try:
            async with asyncio.timeout(20):
                await import_legacy(store, bus)
        except TimeoutError:
            log.warning("importing earlier settings timed out; will retry next start")
    key_for = key_lookup(bus)
    async with httpx.AsyncClient(http2=False, follow_redirects=False, headers={"User-Agent": USER_AGENT}) as client:
        engine = Engine(store, publisher=None, provider_factory=provider_factory(client, key_for))
        service = RuntimeService(bus, engine, list_models=model_lister(client, key_for))
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
