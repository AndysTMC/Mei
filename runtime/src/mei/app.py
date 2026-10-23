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
from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus

from mei import legacy
from mei.capabilities.base import App, Env
from mei.capabilities.catalog import default_registry
from mei.computer import jail as computer_jail
from mei.computer.controller import Desktop, DesktopError
from mei.core.engine import Engine
from mei.desktop import apps as desktop_apps
from mei.desktop.gsettings import GSETTINGS, GSettingsCli
from mei.desktop.notify import BusNotifier
from mei.desktop.pdf import PdfToText
from mei.desktop.media import Mpris
from mei.desktop.sandbox import Sandbox
from mei.desktop.screen import watch_lock
from mei.desktop.system import SystemStatus
from mei.desktop.sound import WPCTL, Wpctl
from mei.ipc import dbus_patch
from mei.ipc.service import RUNTIME_VERSION, RuntimeService
from mei.obs import redact
from mei.paths import cache_home, data_dir, data_home, user_dirs
from mei.protocol import Envelope, ProviderConfig, provider_config
from mei.providers import factory, models
from mei.providers.base import ChatTurn, ModelRequest, Provider, ProviderError, TextDelta
from mei.providers.factory import label_of
from mei.providers.profiles import PROFILES
from mei.secrets import (KeyringLocked, KeyringUnavailable, keyring_state, lookup_provider_key, lookup_secret,
                         store_provider_key, store_secret, unlock_keyring)
from mei.setup import Probes, Setup
from mei.store import repo
from mei.store.db import Store, iso_now, new_id
from mei.voice import jail as voice_jail
from mei.core.fanout import Fanout

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
               volume=Wpctl() if os.access(WPCTL, os.X_OK) else None, runner=Sandbox(), cache_home=cache_home(),
               media=Mpris(bus), status=SystemStatus(home))


class KeyringTokens:
    """The screen session's restore token, in the keyring: whoever holds it can start a session with no
    dialog. A locked or missing keyring reads as no token, so the next session asks the person again."""

    NAME = "screen-session"

    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus

    async def get(self) -> str:
        try:
            return await lookup_secret(self._bus, self.NAME) or ""
        except (KeyringLocked, KeyringUnavailable) as e:
            log.info("no screen session token: %s", e)
            return ""

    async def put(self, token: str) -> None:
        try:
            await store_secret(self._bus, self.NAME, "Mei screen session", token)
        except (KeyringLocked, KeyringUnavailable) as e:
            log.warning("couldn't keep the screen session token (the next session will ask again): %s", e)


def desktop_controller(bus: MessageBus, bridge: Callable) -> Desktop | None:
    """Computer use, where it can run: bubblewrap, xdg-dbus-proxy and the system's Python. None otherwise."""
    missing = computer_jail.missing()
    address = os.environ.get("DBUS_SESSION_BUS_ADDRESS", "")
    if missing or not address:
        log.info("computer use isn't available here: %s", missing or "no session bus address")
        return None

    async def a11y_address() -> str:
        reply = await bus.call(Message(destination="org.a11y.Bus", path="/org/a11y/bus", interface="org.a11y.Bus",
                                       member="GetAddress"))
        if reply.message_type != MessageType.METHOD_RETURN:
            raise DesktopError("unavailable", "the accessibility bus isn't running")
        return str(reply.body[0])

    async def overlay(active: bool) -> None:
        shell = bridge()
        if shell is not None:
            await shell.show_overlay(active)

    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    return Desktop(address, a11y_address, KeyringTokens(bus), runtime / "mei", overlay=overlay,
                   revoked=lambda reason: log.info("computer use stopped: %s", reason))


def voice_controller(engine: Engine, service_ref: Callable[[], RuntimeService | None], client: httpx.AsyncClient,
                     key_for):
    """Voice, where it can run: the local engine installed (the optional `voice` extra, imported only
    then) and bubblewrap for the worker's jail. None otherwise."""
    if not voice_jail.engine_installed() or not voice_jail.available():
        log.info("voice isn't available here (the voice engine or bubblewrap is missing)")
        return None
    from mei.voice.cloud import CloudSpeech
    from mei.voice.controller import VoiceController

    def emit(kind: str, payload: dict) -> None:
        service = service_ref()
        if service is not None:
            service.publish_ephemeral(Envelope(type=kind, event_id=new_id(), epoch=engine.store.epoch, at=iso_now(),
                                               required=False, payload=payload))

    # Test-only (like MEI_DATA_DIR): a recorded file instead of the microphone, and playback captured
    # to a file, so end-to-end tests never open the real microphone or play sound aloud.
    source, sink = os.environ.get("MEI_VOICE_SOURCE_FILE", ""), os.environ.get("MEI_VOICE_SINK_FILE", "")
    extra = {"source_file": source, "source_realtime": True, "sink_file": sink} if source and sink else {}

    def argv(settings, models: Path, gpu_engine: Path | None) -> list[str]:
        return voice_jail.worker_argv(models, gpu_engine=gpu_engine, readable=(Path(source),) if extra else (),
                                      writable=(Path(sink).parent,) if extra else ())

    return VoiceController(engine, emit, argv, load_extra=extra, cloud=CloudSpeech(client, key_for), client=client)


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
        env.desktop = desktop = desktop_controller(bus, env.bridge)
        engine = Engine(store, publisher=None, provider_factory=provider_factory(client, key_for),
                        registry=default_registry(), env=env)
        make_provider = provider_factory(client, key_for)
        setup = Setup(store, setup_probes(bus), data_dir(), RUNTIME_VERSION)
        voice = voice_controller(engine, lambda: holder[0] if holder else None, client, key_for)
        service = RuntimeService(bus, engine, list_models=model_lister(store, client, key_for), setup=setup,
                                 test_provider=provider_tester(store, make_provider), notifier=env.notifier, voice=voice,
                                 desktop=desktop)
        # The service needs the engine and the engine publishes through it (and through voice).
        engine.publisher = Fanout(service, voice) if voice is not None else service
        holder.append(service)
        engine.recover()
        await service.start()
        if voice is not None:
            await voice.apply(repo.get_config(store)[1].voice)
        locked = [c.set_locked for c in (voice, desktop) if c is not None]
        if locked:
            async def lock_changed(is_locked: bool) -> None:
                for changed in locked:
                    await changed(is_locked)

            await watch_lock(bus, lock_changed)
        retention = asyncio.ensure_future(retention_loop(engine))
        disconnected = asyncio.ensure_future(bus.wait_for_disconnect())
        stopped = asyncio.ensure_future(stop.wait())
        done, _ = await asyncio.wait({disconnected, stopped}, return_when=asyncio.FIRST_COMPLETED)
        retention.cancel()
        if desktop is not None:
            await desktop.stop()
        if voice is not None:
            await voice.stop()
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
