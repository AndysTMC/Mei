"""Apps (§9.3): list what's installed and open one, optionally with files or folders."""

import asyncio
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

import msgspec

from mei.core.states import Disposition

from .base import (ActionContext, ActionResult, App, Availability, AVAILABLE, Capability, CapabilityError,
                   CheckResult, Effects, Env, Resource)
from .fs_at import judged_path, look
from .fs_read import resolve_existing

MAX_LISTED = 40
WINDOW_WAIT_S = 6.0
LAUNCH = Effects(mutates="local", undo="n/a")  # it opens a window; closing it is the undo


def find_app(env: Env, wanted: str) -> App:
    apps = env.apps()
    key = wanted.strip().removesuffix(".desktop").lower()
    exact = [a for a in apps if a.id.lower() == key]
    if exact:
        return exact[0]
    named = [a for a in apps if a.name.lower() == key]
    if len(named) == 1:
        return named[0]
    raise CapabilityError("not_found", f"no app called {wanted!r}; use apps_list to find its id")


def aliases(app: App) -> tuple[str, ...]:
    return tuple(dict.fromkeys(n for n in (app.name, app.generic, app.id.rsplit(".", 1)[-1], *app.keywords) if n))


class ListParams(msgspec.Struct, kw_only=True):
    query: Annotated[str, msgspec.Meta(description="Words to match in the app's name or description")] = ""


class AppsList(Capability):
    name = "apps.list"
    summary = "Find installed apps by name or purpose. Gives the app id to open it with."
    Params = ListParams
    idempotent = True

    def describe(self, p: ListParams, env: Env) -> str:
        return f"Look for apps matching “{p.query}”" if p.query else "List installed apps"

    async def run(self, p: ListParams, ctx: ActionContext) -> ActionResult:
        words = p.query.lower().split()
        found = [a for a in ctx.env.apps()
                 if all(w in " ".join((a.id, a.name, a.generic, a.comment, *a.keywords)).lower() for w in words)]
        lines = [f"- {a.name} ({a.id})" + (f": {a.generic or a.comment}" if a.generic or a.comment else "")
                 for a in found[:MAX_LISTED]]
        head = f"{len(found)} app{'s' if len(found) != 1 else ''}" + (f", first {MAX_LISTED}" if len(found) > MAX_LISTED else "")
        return ActionResult(ok=True, observation="\n".join([head, *lines]), summary=f"Found {len(found)} apps")


class LaunchParams(msgspec.Struct, kw_only=True):
    app_id: Annotated[str, msgspec.Meta(description="The app's id from apps_list, e.g. org.gnome.Nautilus")]
    files: Annotated[list[str], msgspec.Meta(max_length=20, description="Files or folders to open in it")] = \
        msgspec.field(default_factory=list)


class AppsLaunch(Capability):
    name = "apps.launch"
    summary = "Open an app, optionally with files or folders (e.g. Files showing ~/Downloads)."
    Params = LaunchParams
    timeout_s = 30.0

    def available(self, env: Env) -> Availability:
        return AVAILABLE if env.launcher is not None else Availability.unavailable("apps can't be opened here")

    def effects(self, p: LaunchParams, env: Env) -> Effects:
        return LAUNCH

    def resources(self, p: LaunchParams, env: Env) -> list[Resource]:
        app = find_app(env, p.app_id)
        found = [Resource(kind="app", value=app.id, access="write", role="app", aliases=aliases(app))]
        for f in p.files:
            found.append(Resource(kind="path", value=str(resolve_existing(env, f)), access="read", role="file"))
        return found

    def describe(self, p: LaunchParams, env: Env) -> str:
        try:
            name = find_app(env, p.app_id).name
        except CapabilityError:
            name = p.app_id
        return f"Open {name}" + (f" with {', '.join(p.files)}" if p.files else "")

    async def run(self, p: LaunchParams, ctx: ActionContext) -> ActionResult:
        env = ctx.env
        app = find_app(env, p.app_id)
        # The app opens files by path, so give it the real paths policy judged, each walked once more
        # without following links just before the launch (fs_at.py): a link swapped in after the
        # check stops the launch instead of opening something else.
        paths = [judged_path(ctx, "file", resolve_existing(env, f), index=i) for i, f in enumerate(p.files)]
        for path in paths:
            if look(env, path) is None:
                raise CapabilityError("not_found", f"{env.show(path)} doesn't exist")
        await env.launcher.launch(app, [_uri(path) for path in paths])
        shown = ", ".join(env.show(path) for path in paths)
        return ActionResult(ok=True, observation=f"Opened {app.name}" + (f" with {shown}" if shown else ""),
                            summary=f"Opened {app.name}" + (f" in {shown}" if shown else ""))

    async def verify(self, p: LaunchParams, result: ActionResult, ctx: ActionContext) -> CheckResult:
        bridge = ctx.env.bridge()
        if bridge is None:
            return CheckResult(status="unverifiable", detail="the Shell isn't connected, so windows can't be seen")
        app = find_app(ctx.env, p.app_id)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + WINDOW_WAIT_S
        while True:
            if any(w.app_id.removesuffix(".desktop") == app.id for w in await bridge.list_windows()):
                return CheckResult(status="passed", detail=f"{app.name} has a window open")
            if loop.time() > deadline:
                return CheckResult(status="failed", detail=f"no {app.name} window appeared")
            await asyncio.sleep(0.25)

    async def probe(self, p: LaunchParams, ctx: ActionContext) -> Disposition:
        bridge = ctx.env.bridge()
        if bridge is None:
            return Disposition.UNKNOWN
        app = find_app(ctx.env, p.app_id)
        windows = await bridge.list_windows()
        return Disposition.CONFIRMED if any(w.app_id.removesuffix(".desktop") == app.id for w in windows) \
            else Disposition.UNKNOWN


def _uri(path: Path) -> str:
    return "file://" + quote(str(path))

