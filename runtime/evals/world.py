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

    async def launch_app(self, app_id: str, uris: list[str]) -> None:
        self.launched.append((app_id, uris))
        name = next((a.name for a in APPS if a.id == app_id), app_id)
        title = Path(unquote(urlparse(uris[0]).path)).name if uris else name
        self.windows.append(Window(app_id=f"{app_id}.desktop", title=title))


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
        self.notifier = FakeNotifier()
        self.gsettings = GSettingsCli(env={"GSETTINGS_BACKEND": "keyfile", "XDG_CONFIG_HOME": str(root / "config")}) \
            if os.access(GSETTINGS, os.X_OK) else None
        self.env = Env(home=self.home, data_dir=root / "mei", data_home=self.home / ".local/share", user_dirs=dirs,
                       gsettings=self.gsettings, bridge=lambda: self.shell, apps=lambda: APPS,
                       launcher=Launcher(lambda: self.shell), notifier=self.notifier,
                       extractor=PdfToText() if PdfToText.available() else None, volume=self.volume)

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
