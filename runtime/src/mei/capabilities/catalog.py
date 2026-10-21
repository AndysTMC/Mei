"""The capabilities Mei offers (§9.3 v1 catalog), in the order the model sees them."""

from .base import Capability
from .fs_read import FsList, FsReadText, FsSearch
from .fs_write import FsEdit, FsMakeDir, FsMove, FsTrash, FsWriteText
from .meta import AskUser, PlanUpdate, TaskFinish
from .registry import Registry


def file_capabilities() -> list[Capability]:
    return [FsList(), FsSearch(), FsReadText(), FsWriteText(), FsEdit(), FsMove(), FsMakeDir(), FsTrash()]


def meta_capabilities() -> list[Capability]:
    return [PlanUpdate(), AskUser(), TaskFinish()]


def default_registry() -> Registry:
    return Registry([*meta_capabilities(), *file_capabilities()])
