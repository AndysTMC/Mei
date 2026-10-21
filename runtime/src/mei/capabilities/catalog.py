"""The capabilities Mei offers (§9.3 v1 catalog), in the order the model sees them."""

from .apps import AppsLaunch, AppsList
from .base import Capability
from .fs_read import FsList, FsReadText, FsSearch
from .fs_write import FsEdit, FsMakeDir, FsMove, FsTrash, FsWriteText
from .meta import AskUser, PlanUpdate, TaskFinish
from .notify import NotifySend
from .registry import Registry
from .settings import SettingsGet, SettingsSet
from .sound import SoundGetVolume, SoundSetVolume


def file_capabilities() -> list[Capability]:
    return [FsList(), FsSearch(), FsReadText(), FsWriteText(), FsEdit(), FsMove(), FsMakeDir(), FsTrash()]


def desktop_capabilities() -> list[Capability]:
    return [AppsList(), AppsLaunch(), SettingsGet(), SettingsSet(), SoundGetVolume(), SoundSetVolume(), NotifySend()]


def meta_capabilities() -> list[Capability]:
    return [PlanUpdate(), AskUser(), TaskFinish()]


def default_registry() -> Registry:
    return Registry([*meta_capabilities(), *file_capabilities(), *desktop_capabilities()])
