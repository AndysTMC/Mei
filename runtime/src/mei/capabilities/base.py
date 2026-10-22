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


DataClass = Literal["none", "metadata", "file_content", "clipboard", "settings", "memory"]
# changed: what policy judged isn't what the path leads to any more (a folder on the way became a link).
ErrorClass = Literal["", "invalid", "not_found", "exists", "permission", "unavailable", "failed", "timeout", "changed"]


# A resource value standing for the conversation's workspace, which `resources()` can't name (it
# doesn't know the conversation); the decision step puts the real path in its place.
WORKSPACE = "{workspace}"


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
    id: int = 0  # the Shell's window id, for focusing it


class BridgePort(Protocol):
    """The Shell extension's narrow bridge (§12.6); absent while no Shell is attached."""

    async def list_windows(self) -> list[Window]: ...
    async def launch_app(self, app_id: str, uris: list[str]) -> None: ...
    async def focus_window(self, window_id: int) -> None: ...
    async def clipboard_get(self) -> str: ...
    async def clipboard_set(self, text: str) -> None: ...
    async def idle_ms(self) -> int: ...


class Player(msgspec.Struct, frozen=True, kw_only=True):
    name: str  # its bus name, org.mpris.MediaPlayer2.<name>
    identity: str  # "Rhythmbox"
    status: str = ""  # Playing, Paused, Stopped
    title: str = ""
    artist: str = ""


class MediaPort(Protocol):
    """Media players on the session bus (MPRIS)."""

    async def players(self) -> list[Player]: ...
    async def control(self, name: str, action: str) -> None: ...


class StatusPort(Protocol):
    async def read(self) -> dict: ...


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


@dataclass(frozen=True)
class Mount:
    path: Path
    writable: bool = False
    fd: int | None = None  # the folder held open (fs_at.folder): bound by fd, so a link swap can't redirect it


@dataclass(frozen=True)
class RunSpec:
    command: str
    cwd: Path
    timeout_s: float
    spill: Path  # where the full output goes
    workspace: Path | None = None  # the conversation's scratch folder, writable, also $HOME inside the jail
    workspace_fd: int | None = None  # the workspace held open, bound by fd
    cwd_fd: int | None = None  # host commands: the judged folder held open, run there
    mounts: tuple[Mount, ...] = ()
    hidden: tuple[Path, ...] = ()  # sensitive files and folders inside the mounts, masked
    network: bool = False
    sandboxed: bool = True  # False: shell.run_host, the person's own session as it is
    # Would Mei hide this file? Folders with a descriptor are watched while the command runs, and a
    # file this says yes to that appears stops it (desktop/watch.py).
    secret: Callable[[Path], bool] | None = None


@dataclass
class RunResult:
    exit_code: int | None  # None: killed (timeout or cancel)
    head: bytes
    tail: bytes
    total_bytes: int
    seconds: float
    timed_out: bool = False
    spilled: Path | None = None
    notes: list[str] = field(default_factory=list)
    secret_appeared: Path | None = None  # stopped: this appeared in a watched folder; the output is withheld


class Runner(Protocol):
    """Runs commands in a jail or on the host (desktop/sandbox.py)."""

    def available(self, sandboxed: bool = True) -> bool: ...
    async def run(self, spec: RunSpec) -> RunResult: ...


class Notifier(Protocol):
    async def notify(self, title: str, body: str) -> int: ...


class TextExtractor(Protocol):
    async def pdf_text(self, file_fd: int, max_chars: int) -> str:
        """The text of the PDF open at `file_fd` (the file judged, opened without following links)."""
        ...


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
    runner: Runner | None = None
    media: MediaPort | None = None
    status: StatusPort | None = None
    cache_home: Path | None = None  # $XDG_CACHE_HOME: task workspaces live under it
    clock: Callable[[], float] = time.time

    @cached_property
    def rules(self) -> PathRules:
        return PathRules(self.home, self.user_dirs, [self.data_dir])

    @property
    def trash_dir(self) -> Path:
        return (self.data_home or self.home / ".local/share") / "Trash"

    def workspace(self, conversation_id: str) -> Path:
        """A conversation's scratch folder for commands: Mei's own, so changes there need no card."""
        return (self.cache_home or self.home / ".cache") / "mei" / "workspaces" / conversation_id

    def artifacts(self, conversation_id: str) -> Path:
        """Where a conversation's large outputs are kept; deleted with the conversation."""
        return self.data_dir / "artifacts" / conversation_id

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
    task_id: str = ""
    # Each path resource's role → where policy judged it really leads (in order: a command can name several
    # folders), as re-checked just before the run. File capabilities act on exactly these (fs_at.py); empty
    # when a capability runs outside the loop.
    judged: dict[str, tuple[str, ...]] = field(default_factory=dict)

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
    always_ask: ClassVar[bool] = False  # a card every time, whatever the preset or grants (shell.run_host)

    def effects(self, p, env: Env) -> Effects:
        return READ_ONLY

    def resources(self, p, env: Env) -> list[Resource]:
        """What it touches. Raises CapabilityError("invalid") for parameters that name nothing usable."""
        return []

    def reads_content(self, p, env: Env) -> list[Path | str]:
        """What its result will carry the contents of (for disclosure to cloud models, §13.5): paths,
        or the value of a non-path resource ("clipboard")."""
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
