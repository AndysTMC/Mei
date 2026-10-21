"""Composition root: wires the store, providers, engine, and D-Bus service, and runs until stopped."""

import asyncio
import logging
import os
import signal
import time
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from pathlib import Path

import httpx
from dbus_fast import BusType
from dbus_fast.aio import MessageBus

from mei import legacy
from mei.capabilities.base import App, Env
from mei.capabilities.catalog import default_registry
from mei.core.engine import Engine
from mei.desktop import apps as desktop_apps
from mei.desktop.gsettings import GSETTINGS, GSettingsCli
from mei.desktop.notify import BusNotifier
from mei.desktop.pdf import PdfToText
from mei.desktop.sound import WPCTL, Wpctl
from mei.ipc import dbus_patch
from mei.ipc.service import RUNTIME_VERSION, RuntimeService
from mei.obs import redact
from mei.paths import data_dir, data_home, user_dirs
from mei.protocol import ProviderConfig, provider_config
from mei.providers import factory, models
from mei.providers.base import ChatTurn, ModelRequest, Provider, ProviderError, TextDelta
from mei.providers.factory import label_of
from mei.providers.profiles import PROFILES
from mei.secrets import (KeyringLocked, KeyringUnavailable, keyring_state, lookup_provider_key, store_provider_key,
                         unlock_keyring)
from mei.setup import Probes, Setup
from mei.store import repo
from mei.store.db import Store

log = logging.getLogger("mei.app")

EXIT_LOCKED = 75  # EX_TEMPFAIL: another instance owns the data directory
USER_AGENT = f"Mei/{RUNTIME_VERSION} (+https://github.com/AndysTMC/Mei)"


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


def model_lister(store: Store, client: httpx.AsyncClient, key_for):
    async def list_for(provider_id: str, url: str) -> dict:
        _revision, config = repo.get_config(store)
        configured = config.providers.get(provider_id)
        if not models.credential_allowed(provider_id, url, configured.url if configured else ""):
            label = PROFILES[provider_id].label
            return {"models": [], "requires_key": False, "from_fallback": False,
                    "error": f"Save this endpoint in Settings first: Mei sends your {label} key only to the "
                             "endpoint saved there."}
        try:
            result = await models.list_models(client, provider_id, url=url, api_key=await key_for(provider_id))
        except ProviderError as e:
            return {"models": [], "requires_key": False, "from_fallback": False, "error": redact(str(e))}
        return {"models": result.models, "requires_key": result.requires_key, "from_fallback": result.from_fallback}

    return list_for


TEST_PROMPT = "Reply with the single word OK."
TEST_TIMEOUT_S = 45
RETENTION_EVERY_S = 3600


def provider_tester(store: Store, make: Callable[[ProviderConfig], Awaitable[Provider]]):
    """One short request to a configured provider, for the setup assistant's Test button."""

    async def test(provider_id: str) -> dict:
        _revision, config = repo.get_config(store)
        cfg = provider_config(config, provider_id or config.active)
        if not cfg.id:
            return {"ok": False, "error": "Choose a provider first.", "ms": 0}
        started, text = time.monotonic(), ""

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        try:
            provider = await make(cfg)
            async with asyncio.timeout(TEST_TIMEOUT_S), \
                    aclosing(provider.stream(ModelRequest([ChatTurn("user", TEST_PROMPT)]))) as events:
                async for event in events:
                    if isinstance(event, TextDelta):
                        text += event.text
                        if len(text) > 200:
                            break  # it answers; that's all the test needs to know
        except ProviderError as e:
            return {"ok": False, "error": redact(str(e)), "ms": elapsed()}
        except TimeoutError:
            return {"ok": False, "error": f"{label_of(cfg)} didn't answer within {TEST_TIMEOUT_S} seconds.",
                    "ms": elapsed()}
        if not text.strip():
            return {"ok": False, "error": f"{label_of(cfg)} answered with no text.", "ms": elapsed()}
        return {"ok": True, "reply": text.strip()[:80], "ms": elapsed()}

    return test


def setup_probes(bus: MessageBus) -> Probes:
    async def has_key(provider_id: str) -> bool | None:
        try:
            return bool(await lookup_provider_key(bus, provider_id))
        except KeyringLocked:
            return None
        except KeyringUnavailable:
            return False

    return Probes(keyring=lambda: keyring_state(bus), has_key=has_key, unlock=lambda: unlock_keyring(bus))


APPS_FRESH_S = 30.0


def app_index() -> Callable[[], list[App]]:
    """Installed apps, rescanned at most every 30 s (installing one shows up without a restart)."""
    cache: tuple[float, list[App]] = (0.0, [])

    def current() -> list[App]:
        nonlocal cache
        if time.monotonic() - cache[0] > APPS_FRESH_S:
            cache = (time.monotonic(), desktop_apps.installed(desktop_apps.app_dirs()))
        return cache[1]

    return current


def desktop_env(bus: MessageBus, bridge: Callable) -> Env:
    """The world capabilities act on. Ports whose tools are missing stay None, and the capabilities
    that need them are left out of what the model is offered."""
    home = Path.home()
    return Env(home=home, data_dir=data_dir(), data_home=data_home(), user_dirs=user_dirs(home),
               gsettings=GSettingsCli() if os.access(GSETTINGS, os.X_OK) else None, bridge=bridge, apps=app_index(),
               launcher=desktop_apps.Launcher(bridge), notifier=BusNotifier(bus),
               extractor=PdfToText() if PdfToText.available() else None,
               volume=Wpctl() if os.access(WPCTL, os.X_OK) else None)


async def retention_loop(engine: Engine) -> None:
    while True:
        try:
            engine.apply_retention()
        except Exception:
            log.exception("applying the retention setting failed")
        await asyncio.sleep(RETENTION_EVERY_S)


async def import_legacy(store: Store, bus: MessageBus) -> None:
    keyring = legacy.Keyring(store=lambda pid, key: store_provider_key(bus, pid, key),
                             lookup=lambda pid: lookup_provider_key(bus, pid))
    report = await legacy.run(store, data_dir(), legacy.DconfCli(), keyring)
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
        holder: list[RuntimeService] = []  # the service owns the Shell bridge; the env asks it when needed
        env = desktop_env(bus, lambda: holder[0].bridge if holder else None)
        engine = Engine(store, publisher=None, provider_factory=provider_factory(client, key_for),
                        registry=default_registry(), env=env)
        make_provider = provider_factory(client, key_for)
        setup = Setup(store, setup_probes(bus), data_dir(), RUNTIME_VERSION)
        service = RuntimeService(bus, engine, list_models=model_lister(store, client, key_for), setup=setup,
                                 test_provider=provider_tester(store, make_provider))
        engine.publisher = service  # the service needs the engine and the engine publishes through it
        holder.append(service)
        engine.recover()
        await service.start()
        retention = asyncio.ensure_future(retention_loop(engine))
        disconnected = asyncio.ensure_future(bus.wait_for_disconnect())
        stopped = asyncio.ensure_future(stop.wait())
        done, _ = await asyncio.wait({disconnected, stopped}, return_when=asyncio.FIRST_COMPLETED)
        retention.cancel()
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
