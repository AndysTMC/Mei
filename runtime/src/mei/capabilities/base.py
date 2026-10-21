"""What a capability is (architecture §9.1).

A capability declares its effects as independent attributes computed from its parameters and the
observed world, never from what the model says it does; the policy engine decides from those. It
runs against an `Env` of ports, so tests give it a fake world and the runtime gives it the desktop.
"""

import os
import time
from abc import ABC, abstractmethod
from functools import cached_property
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Literal, Protocol

import msgspec

from mei.core.states import Disposition
from mei.policy.paths import PathRules


class Effects(msgspec.Struct, frozen=True, kw_only=True):
    mutates: Literal["no", "local", "external", "unknown"] = "no"
    undo: Literal["n/a", "recorded", "none"] = "n/a"  # "recorded" only when an undo record is really kept
    visibility: Literal["private", "others"] = "private"  # can other people see the result?
    disclosure: Literal["none", "local", "off_machine"] = "none"  # does data move somewhere new?
    loses_data: bool = False  # can it destroy data without an undo?


READ_ONLY = Effects()
LOCAL_UNDOABLE = Effects(mutates="local", undo="recorded")


class Resource(msgspec.Struct, frozen=True, kw_only=True):
    """Something an action touches: an absolute path, an app id, or a `schema key` setting."""

    kind: Literal["path", "app", "setting", "memory"]
    value: str
    access: Literal["read", "write"]
    role: str = ""  # which parameter it came from ("source", "destination"), for the approval card
    # Words that name it when a person says them: an app's name ("Files"), a setting's ("dark mode").
    aliases: tuple[str, ...] = ()


DataClass = Literal["none", "metadata", "file_content", "settings", "memory"]
ErrorClass = Literal["", "invalid", "not_found", "exists", "permission", "unavailable", "failed", "timeout"]


class ActionResult(msgspec.Struct, kw_only=True):
    ok: bool
    observation: str  # what the model sees, already bounded
    summary: str = ""  # one line for the person ("Moved invoice.pdf to Invoices/2026")
    error_class: ErrorClass = ""
    undo: dict | None = None  # the capability's own record of how to reverse it
    data_class: DataClass = "metadata"  # what kind of data the observation holds (§13.5)
    trust: Literal["trusted", "untrusted"] = "trusted"  # untrusted: content others could have written
    sources: list[str] = msgspec.field(default_factory=list)  # paths whose content is in the observation


class CheckResult(msgspec.Struct, frozen=True, kw_only=True):
    """A capability's postcondition, or a task criterion's check (§8.5)."""

    status: Literal["passed", "failed", "unverifiable"]
    detail: str = ""


@dataclass(frozen=True)
class Availability:
    ok: bool
    reason: str = ""

    @classmethod
    def unavailable(cls, reason: str) -> "Availability":
        return cls(False, reason)


AVAILABLE = Availability(True)


# ── Ports: the parts of the desktop capabilities reach through ──────────────


class GSettingsPort(Protocol):
    async def get(self, schema: str, key: str) -> str: ...  # GVariant text
    async def set(self, schema: str, key: str, value: str) -> None: ...
    async def range(self, schema: str, key: str) -> str: ...


class Window(msgspec.Struct, frozen=True, kw_only=True):
    app_id: str
    title: str
    focused: bool = False


class BridgePort(Protocol):
    """The Shell extension's narrow bridge (§12.6); absent while no Shell is attached."""

    async def list_windows(self) -> list[Window]: ...
    async def launch_app(self, app_id: str, uris: list[str]) -> None: ...


@dataclass(frozen=True)
class App:
    id: str  # the desktop file id, "org.gnome.Nautilus"
    name: str  # "Files"
    generic: str = ""  # "File Manager"
    comment: str = ""
    keywords: tuple[str, ...] = ()
    path: Path = field(default=Path())


class Launcher(Protocol):
    async def launch(self, app: App, uris: list[str]) -> None: ...


class Volume(Protocol):
    async def get(self) -> tuple[int, bool]: ...  # (percent, muted)
    async def set(self, percent: int, muted: bool) -> None: ...


class MemoryPort(Protocol):
    """Mei's memory and history, as the memory tools see them (store/memory.py behind it)."""

    def search(self, text: str, limit: int) -> list[dict]: ...
    def history(self, text: str, limit: int) -> list[dict]: ...
    def get(self, memory_id: str) -> dict | None: ...
    def archive(self, memory_id: str) -> dict | None: ...


class Notifier(Protocol):
    async def notify(self, title: str, body: str) -> int: ...


class TextExtractor(Protocol):
    async def pdf_text(self, path: Path, max_chars: int) -> str: ...


@dataclass
class Env:
    home: Path
    data_dir: Path  # Mei's own store: backups of overwritten files go under it
    data_home: Path | None = None  # $XDG_DATA_HOME; the trash lives there
    user_dirs: dict[str, Path] = field(default_factory=dict)  # "DOWNLOAD" → ~/Downloads (xdg-user-dirs)
    gsettings: GSettingsPort | None = None
    bridge: Callable[[], BridgePort | None] = lambda: None
    apps: Callable[[], list[App]] = lambda: []
    launcher: Launcher | None = None
    notifier: Notifier | None = None
    extractor: TextExtractor | None = None
    volume: Volume | None = None
    memory: MemoryPort | None = None
    clock: Callable[[], float] = time.time

    @cached_property
    def rules(self) -> PathRules:
        return PathRules(self.home, self.user_dirs, [self.data_dir])

    @property
    def trash_dir(self) -> Path:
        return (self.data_home or self.home / ".local/share") / "Trash"

    def path(self, value: str) -> Path:
        """A model-given path, made absolute: `~` is home, and relative paths start at home."""
        text = value.strip()
        if text == "~" or text.startswith("~/"):
            text = str(self.home) + text[1:]
        elif text.startswith("~"):  # `~otheruser`: not ours to guess at
            raise ValueError(f"unsupported path {value!r}")
        p = Path(text)
        if not p.is_absolute():
            p = self.home / p
        return Path(os.path.normpath(p))

    def show(self, path: Path | str) -> str:
        """A path as people read it: `~/Downloads/x.pdf`."""
        text = str(path)
        home = str(self.home)
        return "~" + text[len(home):] if text == home or text.startswith(home + "/") else text


@dataclass
class ActionContext:
    env: Env
    action_id: str
    conversation_id: str = "none"

    @property
    def backup_dir(self) -> Path:
        """Copies of what this action overwrote. Kept per conversation, and deleted with it."""
        return backups_dir(self.env, self.conversation_id) / self.action_id


def backups_dir(env: Env, conversation_id: str) -> Path:
    return env.data_dir / "backups" / conversation_id


class CapabilityError(Exception):
    """A capability refused or failed in a way the model should hear about."""

    def __init__(self, error_class: ErrorClass, message: str) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.message = message


class Capability(ABC):
    name: ClassVar[str]  # "fs.move"
    version: ClassVar[int] = 1
    summary: ClassVar[str]  # model-facing, one or two sentences
    Params: ClassVar[type[msgspec.Struct]]
    idempotent: ClassVar[bool] = False
    timeout_s: ClassVar[float] = 30.0
    meta: ClassVar[bool] = False  # plan.update, ask_user, task.finish: handled by the loop, not run

    def effects(self, p, env: Env) -> Effects:
        return READ_ONLY

    def resources(self, p, env: Env) -> list[Resource]:
        """What it touches. Raises CapabilityError("invalid") for parameters that name nothing usable."""
        return []

    def reads_content(self, p, env: Env) -> list[Path]:
        """Paths whose contents its result will carry (for disclosure to cloud models, §13.5)."""
        return []

    def available(self, env: Env) -> Availability:
        return AVAILABLE

    @abstractmethod
    def describe(self, p, env: Env) -> str:
        """What it will do, in words for the approval card."""

    async def run(self, p, ctx: ActionContext) -> ActionResult:
        raise NotImplementedError(f"{self.name} is handled by the loop")

    async def verify(self, p, result: ActionResult, ctx: ActionContext) -> CheckResult | None:
        """Did it do what it says (the postcondition)? None: nothing to check."""
        return None

    async def probe(self, p, ctx: ActionContext) -> Disposition:
        """After a crash mid-run: did the world change? Used only for non-idempotent capabilities."""
        return Disposition.UNKNOWN
