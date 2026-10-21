"""The capabilities Mei offers (§9.3 v1 catalog), in the order the model sees them."""

from .apps import AppsLaunch, AppsList
from .base import Capability
from .fs_read import FsList, FsReadText, FsSearch
from .fs_write import FsEdit, FsMakeDir, FsMove, FsTrash, FsWriteText
from .memory import HistorySearch, MemoryForget, MemorySave, MemorySearch
from .meta import AskUser, PlanUpdate, TaskFinish
from .notify import NotifySend
from .os import (ClipboardRead, ClipboardWrite, MediaControl, MediaStatus, SystemStatusCap, WindowsFocus,
                 WindowsList)
from .registry import Registry
from .settings import SettingsGet, SettingsSet
from .shell import ShellOutput, ShellRun, ShellRunHost
from .sound import SoundGetVolume, SoundSetVolume


def file_capabilities() -> list[Capability]:
    return [FsList(), FsSearch(), FsReadText(), FsWriteText(), FsEdit(), FsMove(), FsMakeDir(), FsTrash()]


def shell_capabilities() -> list[Capability]:
    return [ShellRun(), ShellOutput(), ShellRunHost()]


def desktop_capabilities() -> list[Capability]:
    return [AppsList(), AppsLaunch(), WindowsList(), WindowsFocus(), ClipboardRead(), ClipboardWrite(), SettingsGet(),
            SettingsSet(), SoundGetVolume(), SoundSetVolume(), MediaStatus(), MediaControl(), SystemStatusCap(),
            NotifySend()]


def meta_capabilities() -> list[Capability]:
    return [PlanUpdate(), AskUser(), TaskFinish()]


def memory_capabilities() -> list[Capability]:
    return [MemorySave(), MemorySearch(), MemoryForget(), HistorySearch()]


MEMORY_TOOLS = frozenset({"memory.save", "memory.search", "memory.forget"})  # hidden while memory is off


def default_registry() -> Registry:
    return Registry([*meta_capabilities(), *memory_capabilities(), *file_capabilities(), *shell_capabilities(),
                     *desktop_capabilities()])
