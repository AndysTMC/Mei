"""Windows, the clipboard, media players, and the system's state (§9.3 "Apps & OS").

Windows and the clipboard go through the Shell bridge: GNOME offers no other way for a background
process to read or set them on Wayland. Window titles and clipboard text are written by others (a
web page's title, text copied from anywhere), so they come back as untrusted.
"""

from typing import Annotated, Literal

import msgspec

from mei.core.states import Disposition

from .base import (LOCAL_UNDOABLE, ActionContext, ActionResult, Availability, AVAILABLE, Capability,
                   CapabilityError, CheckResult, Effects, Env, Resource)

CLIPBOARD_WORDS = ("clipboard", "copied", "paste", "copy")
MEDIA_WORDS = ("music", "song", "media", "player", "track", "playing", "podcast", "video")
MAX_CLIPBOARD = 20_000


def _needs_bridge(env: Env) -> Availability:
    return AVAILABLE if env.bridge() is not None else Availability.unavailable("the Shell isn't connected")


def _bridge(ctx: ActionContext):
    bridge = ctx.env.bridge()
    if bridge is None:
        raise CapabilityError("unavailable", "the Shell isn't connected right now")
    return bridge


class NoParams(msgspec.Struct, kw_only=True):
    pass


class WindowsList(Capability):
    name = "windows.list"
    summary = "List the open windows: app, title, and which has focus."
    Params = NoParams
    idempotent = True

    def available(self, env: Env) -> Availability:
        return _needs_bridge(env)

    def describe(self, p: NoParams, env: Env) -> str:
        return "List open windows"

    async def run(self, p: NoParams, ctx: ActionContext) -> ActionResult:
        windows = await _bridge(ctx).list_windows()
        lines = [f"- [{w.id}] {w.title} ({w.app_id.removesuffix('.desktop') or 'unknown app'})"
                 + (" — focused" if w.focused else "") for w in windows]
        return ActionResult(ok=True, observation="\n".join(lines) or "No windows are open.",
                            summary=f"Listed {len(windows)} windows", trust="untrusted")


class FocusParams(msgspec.Struct, kw_only=True):
    window_id: Annotated[int, msgspec.Meta(description="The id from windows_list")]


class WindowsFocus(Capability):
    name = "windows.focus"
    summary = "Bring a window to the front."
    Params = FocusParams

    def available(self, env: Env) -> Availability:
        return _needs_bridge(env)

    def effects(self, p: FocusParams, env: Env) -> Effects:
        return Effects(mutates="local", undo="n/a")  # trivially undone: the person switches back

    def resources(self, p: FocusParams, env: Env) -> list[Resource]:
        return [Resource(kind="app", value=f"window {p.window_id}", access="write", role="window",
                         aliases=("window", "switch to", "bring up"))]

    def describe(self, p: FocusParams, env: Env) -> str:
        return f"Bring window {p.window_id} to the front"

    async def run(self, p: FocusParams, ctx: ActionContext) -> ActionResult:
        bridge = _bridge(ctx)
        await bridge.focus_window(p.window_id)
        return ActionResult(ok=True, observation=f"Window {p.window_id} is in front.", summary="Switched window")

    async def verify(self, p: FocusParams, result: ActionResult, ctx: ActionContext) -> CheckResult:
        focused = [w for w in await _bridge(ctx).list_windows() if w.focused]
        ok = bool(focused) and focused[0].id == p.window_id
        return CheckResult(status="passed" if ok else "failed")


CLIPBOARD = Resource(kind="setting", value="clipboard", access="read", role="clipboard", aliases=CLIPBOARD_WORDS)


class ClipboardRead(Capability):
    name = "clipboard.read"
    summary = "Read the text on the clipboard."
    Params = NoParams
    idempotent = True

    def available(self, env: Env) -> Availability:
        return _needs_bridge(env)

    def resources(self, p: NoParams, env: Env) -> list[Resource]:
        return [CLIPBOARD]

    def reads_content(self, p: NoParams, env: Env) -> list[str]:
        return ["clipboard"]

    def describe(self, p: NoParams, env: Env) -> str:
        return "Read the clipboard"

    async def run(self, p: NoParams, ctx: ActionContext) -> ActionResult:
        text = (await _bridge(ctx).clipboard_get())[:MAX_CLIPBOARD]
        return ActionResult(ok=True, observation=text or "(the clipboard has no text)", summary="Read the clipboard",
                            data_class="clipboard", trust="untrusted")


class ClipboardWriteParams(msgspec.Struct, kw_only=True):
    text: Annotated[str, msgspec.Meta(max_length=MAX_CLIPBOARD)]


class ClipboardWrite(Capability):
    name = "clipboard.write"
    summary = "Put text on the clipboard, ready to paste (what was there before is kept for undo)."
    Params = ClipboardWriteParams
    idempotent = True

    def available(self, env: Env) -> Availability:
        return _needs_bridge(env)

    def effects(self, p: ClipboardWriteParams, env: Env) -> Effects:
        return LOCAL_UNDOABLE

    def resources(self, p: ClipboardWriteParams, env: Env) -> list[Resource]:
        return [Resource(kind="setting", value="clipboard", access="write", role="clipboard", aliases=CLIPBOARD_WORDS)]

    def describe(self, p: ClipboardWriteParams, env: Env) -> str:
        return f"Copy {len(p.text)} characters to the clipboard"

    async def run(self, p: ClipboardWriteParams, ctx: ActionContext) -> ActionResult:
        bridge = _bridge(ctx)
        old = await bridge.clipboard_get()
        await bridge.clipboard_set(p.text)
        return ActionResult(ok=True, observation="Copied to the clipboard.", summary="Copied text to the clipboard",
                            undo={"kind": "clipboard", "old": old[:MAX_CLIPBOARD]})

    async def verify(self, p: ClipboardWriteParams, result: ActionResult, ctx: ActionContext) -> CheckResult:
        ok = await _bridge(ctx).clipboard_get() == p.text
        return CheckResult(status="passed" if ok else "failed")

    async def probe(self, p: ClipboardWriteParams, ctx: ActionContext) -> Disposition:
        return Disposition.CONFIRMED if await _bridge(ctx).clipboard_get() == p.text else Disposition.NONE


def _needs_media(env: Env) -> Availability:
    return AVAILABLE if env.media is not None else Availability.unavailable("media players can't be reached")


class MediaStatus(Capability):
    name = "media.status"
    summary = "What the media players are playing (MPRIS players such as Rhythmbox, Spotify, a browser)."
    Params = NoParams
    idempotent = True

    def available(self, env: Env) -> Availability:
        return _needs_media(env)

    def describe(self, p: NoParams, env: Env) -> str:
        return "Check what's playing"

    async def run(self, p: NoParams, ctx: ActionContext) -> ActionResult:
        players = await ctx.env.media.players()
        lines = [f"- {pl.identity} ({pl.name}): {pl.status or 'unknown'}"
                 + (f" — {pl.title}" + (f" by {pl.artist}" if pl.artist else "") if pl.title else "") for pl in players]
        # Track titles come from files and streams others named.
        return ActionResult(ok=True, observation="\n".join(lines) or "No media player is running.",
                            summary=f"Checked {len(players)} players", trust="untrusted")


class MediaParams(msgspec.Struct, kw_only=True):
    action: Literal["play", "pause", "play_pause", "stop", "next", "previous"]
    player: Annotated[str, msgspec.Meta(description="Player name from media_status; default: the one playing")] = ""


class MediaControl(Capability):
    name = "media.control"
    summary = "Play, pause, stop, or skip in a media player."
    Params = MediaParams

    def available(self, env: Env) -> Availability:
        return _needs_media(env)

    def effects(self, p: MediaParams, env: Env) -> Effects:
        return Effects(mutates="local", undo="n/a")  # pressing the opposite button undoes it

    def resources(self, p: MediaParams, env: Env) -> list[Resource]:
        words = (*MEDIA_WORDS, p.action.replace("_", " "), *((p.player,) if p.player else ()))
        return [Resource(kind="app", value=f"media player {p.player or 'current'}", access="write", role="player",
                         aliases=words)]

    def describe(self, p: MediaParams, env: Env) -> str:
        return f"{p.action.replace('_', '/').capitalize()} {p.player or 'the media player'}"

    async def run(self, p: MediaParams, ctx: ActionContext) -> ActionResult:
        players = await ctx.env.media.players()
        if not players:
            raise CapabilityError("not_found", "no media player is running")
        chosen = next((pl for pl in players if p.player and p.player.lower() in (pl.name.lower(), pl.identity.lower())),
                      None) if p.player else next((pl for pl in players if pl.status == "Playing"), players[0])
        if chosen is None:
            raise CapabilityError("not_found", f"no player called {p.player!r}")
        await ctx.env.media.control(chosen.name, p.action)
        return ActionResult(ok=True, observation=f"{p.action.replace('_', '/')} sent to {chosen.identity}.",
                            summary=f"{p.action.replace('_', '/').capitalize()}: {chosen.identity}")


class SystemStatusCap(Capability):
    name = "system.status"
    summary = "The computer's state: battery, free disk space, memory, load, and how long since the person was active."
    Params = NoParams
    idempotent = True

    def available(self, env: Env) -> Availability:
        return AVAILABLE if env.status is not None else Availability.unavailable("status isn't available")

    def describe(self, p: NoParams, env: Env) -> str:
        return "Check the computer's status"

    async def run(self, p: NoParams, ctx: ActionContext) -> ActionResult:
        status = await ctx.env.status.read()
        bridge = ctx.env.bridge()
        if bridge is not None:
            status["idle_s"] = round(await bridge.idle_ms() / 1000)
        lines = [f"{key}: {value}" for key, value in status.items()]
        return ActionResult(ok=True, observation="\n".join(lines), summary="Checked the computer's status")

