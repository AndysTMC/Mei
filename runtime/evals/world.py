"""A throwaway desktop for one eval task: a home with the usual folders, settings on a private
keyfile backend, apps that open into a recorded window list, a volume, and the real sandboxed PDF
reader. Nothing touches the person's own files or settings."""

import datetime
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from mei.capabilities.base import App, Env, Window
from mei.desktop.apps import Launcher
from mei.desktop.gsettings import GSETTINGS, GSettingsCli
from mei.desktop.pdf import PdfToText
from mei.desktop.sandbox import Sandbox
from mei.store.db import Store

from .pdf import write_pdf

APPS = [App(id="org.gnome.Nautilus", name="Files", generic="File Manager", keywords=("folder", "explorer")),
        App(id="org.gnome.TextEditor", name="Text Editor", keywords=("text", "notes")),
        App(id="org.gnome.Calculator", name="Calculator", keywords=("math",))]


class FakeShell:
    """Opens apps into a window list, as the Shell bridge reports them."""

    def __init__(self) -> None:
        self.windows: list[Window] = []
        self.launched: list[tuple[str, list[str]]] = []

    async def list_windows(self) -> list[Window]:
        return list(self.windows)

    async def monitors(self) -> list[dict]:
        return [{"x": 0, "y": 0, "width": 1920, "height": 1080, "scale": 1.0}]

    async def launch_app(self, app_id: str, uris: list[str]) -> None:
        self.launched.append((app_id, uris))
        name = next((a.name for a in APPS if a.id == app_id), app_id)
        title = Path(unquote(urlparse(uris[0]).path)).name if uris else name
        self.windows.append(Window(app_id=f"{app_id}.desktop", title=title))


class FakeDesktop:
    """A window on screen for computer-use tasks: its controls and text as the desktop worker would
    report them (never a picture: a live model would be sent a fake image). Acts are recorded."""

    def __init__(self, title: str, app: str, nodes: list[dict]) -> None:
        self.title, self.app, self.nodes = title, app, nodes
        self.acts: list[tuple] = []
        self._n = 0

    def person_active(self, idle_ms: int) -> bool:
        return False

    async def observe(self, window: dict, monitors: list, *, picture: bool, max_nodes: int = 250) -> dict:
        self._n += 1
        return {"token": f"s{self._n}", "app": self.app, "title": self.title, "nodes": self.nodes}

    async def act(self, token: str, action: str, **kw) -> dict:
        self.acts.append((action, kw.get("element"), kw.get("text")))
        return {"how": "accessibility", "changes": [], "token": "", "nodes": []}

    def seen(self, token: str):
        from mei.computer.controller import Seen
        if token != f"s{self._n}":
            return None
        return Seen(token, {"id": 1, "title": self.title}, self.app, {n["id"]: n for n in self.nodes})


class FakeVolume:
    def __init__(self) -> None:
        self.level = (50, False)

    async def get(self) -> tuple[int, bool]:
        return self.level

    async def set(self, percent: int, muted: bool) -> None:
        self.level = (percent, muted)


class FakeNotifier:
    def __init__(self) -> None:
        self.shown: list[tuple[str, str]] = []

    async def notify(self, title: str, body: str) -> int:
        self.shown.append((title, body))
        return len(self.shown)


class World:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        dirs = {key: self.home / name for key, name in (("DOWNLOAD", "Downloads"), ("DOCUMENTS", "Documents"),
                                                         ("PICTURES", "Pictures"), ("MUSIC", "Music"),
                                                         ("DESKTOP", "Desktop"))}
        for folder in dirs.values():
            folder.mkdir(parents=True)
        self.shell = FakeShell()
        self.volume = FakeVolume()
        self.store: Store | None = None  # the runtime's store, once a run starts (checks read memories from it)
        self.notifier = FakeNotifier()
        self.gsettings = GSettingsCli(env={"GSETTINGS_BACKEND": "keyfile", "XDG_CONFIG_HOME": str(root / "config")}) \
            if os.access(GSETTINGS, os.X_OK) else None
        self.env = Env(home=self.home, data_dir=root / "mei", data_home=self.home / ".local/share", user_dirs=dirs,
                       gsettings=self.gsettings, bridge=lambda: self.shell, apps=lambda: APPS,
                       launcher=Launcher(lambda: self.shell), notifier=self.notifier,
                       extractor=PdfToText() if PdfToText.available() else None, volume=self.volume,
                       runner=Sandbox(), cache_home=self.home / ".cache")

    def path(self, value: str) -> Path:
        return self.env.path(value)

    def put(self, path: str, text: str = "", *, days_old: float = 0) -> Path:
        p = self.path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        _age(p, days_old)
        return p

    def put_pdf(self, path: str, lines: list[str], *, days_old: float = 0) -> Path:
        p = self.path(path)
        write_pdf(p, lines)
        _age(p, days_old)
        return p

    def show_window(self, title: str, app_id: str, app: str, nodes: list[dict]) -> FakeDesktop:
        """A window on screen, with computer use on: Mei can look at it and act in it."""
        self.shell.windows.append(Window(app_id=app_id, title=title, focused=True, id=1, pid=1,
                                         buffer={"x": 0, "y": 0, "width": 1280, "height": 800}))
        self.env.desktop = FakeDesktop(title, app, nodes)
        return self.env.desktop

    async def setting(self, schema: str, key: str) -> str:
        return await self.gsettings.get(schema, key) if self.gsettings else ""

    async def set_setting(self, schema: str, key: str, value: str) -> None:
        if self.gsettings:
            await self.gsettings.set(schema, key, value)


def last_week_days_ago(weekday: int) -> float:
    """How many days ago that weekday of last week was (0 = Monday), at noon."""
    now = datetime.datetime.now()
    monday = (now - datetime.timedelta(days=now.weekday() + 7)).replace(hour=12, minute=0, second=0, microsecond=0)
    return (now - (monday + datetime.timedelta(days=weekday))).total_seconds() / 86400


def _age(path: Path, days_old: float) -> None:
    if days_old:
        when = datetime.datetime.now().timestamp() - days_old * 86400
        os.utime(path, (when, when))
