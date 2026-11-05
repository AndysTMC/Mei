"""Installed applications, from their .desktop files (Desktop Entry Specification 1.5), and
launching them.

Launching goes through the Shell when it is attached (the app lands in its own scope with focus,
as if the person had opened it); otherwise `gio launch` runs inside a transient user scope, so an
app Mei opened isn't stopped when Mei's own service restarts.
"""

import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from mei.capabilities.base import App, BridgePort

from .run import checked, user_manager

GIO = "/usr/bin/gio"
SYSTEMD_RUN = "/usr/bin/systemd-run"


def app_dirs(env: dict[str, str] | None = None) -> list[Path]:
    """`applications` folders in XDG precedence order: the user's data home first."""
    env = env if env is not None else dict(os.environ)
    home = env.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    dirs = env.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [Path(d) / "applications" for d in [home, *dirs.split(":")] if os.path.isabs(d)]


def installed(dirs: list[Path], desktop: str = "GNOME") -> list[App]:
    seen: dict[str, App | None] = {}
    for root in dirs:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.desktop")):
            app_id = str(path.relative_to(root).with_suffix("")).replace("/", "-")
            if app_id in seen:
                continue  # a higher-priority folder already decided it (possibly by hiding it)
            seen[app_id] = _parse(path, app_id, desktop)
    return sorted((a for a in seen.values() if a is not None), key=lambda a: a.name.lower())


def _parse(path: Path, app_id: str, desktop: str) -> App | None:
    try:
        entry = _entry(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if entry.get("Type") != "Application" or entry.get("NoDisplay") == "true" or entry.get("Hidden") == "true":
        return None
    only = [d for d in entry.get("OnlyShowIn", "").split(";") if d]
    if (only and desktop not in only) or desktop in entry.get("NotShowIn", "").split(";"):
        return None
    try_exec = entry.get("TryExec")
    if try_exec and not (shutil.which(try_exec) if "/" not in try_exec else os.access(try_exec, os.X_OK)):
        return None
    if not entry.get("Name"):
        return None
    return App(app_id, entry["Name"], entry.get("GenericName", ""), entry.get("Comment", ""),
               tuple(k for k in entry.get("Keywords", "").split(";") if k), path)


def _entry(text: str) -> dict[str, str]:
    """The [Desktop Entry] group's unlocalized keys."""
    values: dict[str, str] = {}
    group = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            group = line[1:-1]
            continue
        if group != "Desktop Entry" or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if "[" not in key:
            values.setdefault(key, value)
    return values


class Launcher:
    def __init__(self, bridge: Callable[[], BridgePort | None] = lambda: None, gio: str = GIO,
                 systemd_run: str = SYSTEMD_RUN) -> None:
        self._bridge = bridge
        self._gio = gio
        self._systemd_run = systemd_run if os.access(systemd_run, os.X_OK) and user_manager() else None

    async def launch(self, app: App, uris: list[str]) -> None:
        bridge = self._bridge()
        if bridge is not None:
            await bridge.launch_app(app.id, uris)
            return
        argv = [self._gio, "launch", str(app.path), *uris]
        if self._systemd_run:
            unit = f"app-mei-{_unit(app.id)}-{uuid.uuid4().hex[:8]}"
            argv = [self._systemd_run, "--user", "--scope", "--quiet", "--collect", f"--unit={unit}", "--", *argv]
        await checked(argv, timeout=20.0)


def _unit(app_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in app_id)[:60]
