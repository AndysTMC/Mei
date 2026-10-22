"""Changing the file system: write, edit, move, make folders, trash (§9.3).

Nothing here destroys data: overwritten files are backed up first, moves never replace an
existing file, and deleting means the freedesktop trash. Each action keeps an undo record, so its
effects are `local` with `undo=recorded`, and each can check its own postcondition and, after a
crash mid-run, probe whether it happened. Every change goes through the folders policy judged,
held open, so a link swapped in after the check can't send it elsewhere (fs_at.py).
"""

import datetime
import hashlib
import os
import stat
from pathlib import Path
from typing import Annotated
from urllib.parse import quote, unquote

import msgspec

from mei.core.states import Disposition

from .base import (LOCAL_UNDOABLE, ActionContext, ActionResult, Capability, CapabilityError, CheckResult, Effects,
                   Env, Resource)
from .fs_at import backup, entry, folder, judged_path, move_at, open_file, rename_noreplace, temp_name, write_atomic
from .fs_read import resolve_existing

MAX_WRITE_CHARS = 1_000_000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def target(env: Env, value: str) -> Path:
    try:
        return env.path(value)
    except ValueError as e:
        raise CapabilityError("invalid", str(e)) from None


def write_resource(env: Env, value: str, role: str) -> list[Resource]:
    return [Resource(kind="path", value=str(target(env, value)), access="write", role=role)]


def _clean_temp(path: Path, action_id: str) -> None:
    path.with_name(temp_name(action_id)).unlink(missing_ok=True)


# ── fs.write_text ───────────────────────────────────────────────────────────


class WriteParams(msgspec.Struct, kw_only=True):
    path: str
    text: Annotated[str, msgspec.Meta(max_length=MAX_WRITE_CHARS)]
    overwrite: Annotated[bool, msgspec.Meta(description="Replace the file if it exists (a backup is kept)")] = False


class FsWriteText(Capability):
    name = "fs.write_text"
    summary = "Write a text file, creating missing folders. Set overwrite to replace an existing file."
    Params = WriteParams

    def effects(self, p: WriteParams, env: Env) -> Effects:
        return LOCAL_UNDOABLE

    def resources(self, p: WriteParams, env: Env) -> list[Resource]:
        return write_resource(env, p.path, "path")

    def describe(self, p: WriteParams, env: Env) -> str:
        verb = "Replace" if p.overwrite else "Create"
        return f"{verb} {p.path} ({len(p.text)} characters)"

    async def run(self, p: WriteParams, ctx: ActionContext) -> ActionResult:
        env = ctx.env
        path = judged_path(ctx, "path", target(env, p.path))
        exists = CapabilityError("exists", f"{env.show(path)} already exists; set overwrite to replace it")
        with folder(env, path.parent, create=True) as parent:
            st = entry(parent.fd, path.name)
            if st is not None and stat.S_ISDIR(st.st_mode):
                raise CapabilityError("invalid", f"{env.show(path)} is a folder")
            saved = None
            if st is not None:
                if not p.overwrite:
                    raise exists
                file_fd = open_file(env, parent.fd, path.name, path)
                try:
                    saved = backup(ctx, file_fd, path.name)
                finally:
                    os.close(file_fd)
            try:
                write_atomic(parent.fd, path.name, p.text.encode(), ctx.action_id, replace=st is not None, mode_of=st)
            except FileExistsError:
                raise exists from None  # made meanwhile: still never replaced without asking
            created = parent.created
        verb = "Replaced" if saved else "Created"
        return ActionResult(ok=True, observation=f"{verb} {env.show(path)} ({len(p.text)} characters)",
                            summary=f"{verb} {env.show(path)}",
                            undo={"kind": "write", "path": str(path), "backup": saved, "created_dirs": created})

    async def verify(self, p: WriteParams, result: ActionResult, ctx: ActionContext) -> CheckResult:
        path = target(ctx.env, p.path)
        ok = path.is_file() and sha256(path.read_bytes()) == sha256(p.text.encode())
        return CheckResult(status="passed" if ok else "failed", detail="" if ok else "the file doesn't hold the text")

    async def probe(self, p: WriteParams, ctx: ActionContext) -> Disposition:
        path = target(ctx.env, p.path)
        _clean_temp(path, ctx.action_id)
        if path.is_file() and sha256(path.read_bytes()) == sha256(p.text.encode()):
            return Disposition.CONFIRMED
        return Disposition.NONE  # writes replace the file in one step: either the new text is there or it isn't


# ── fs.edit ─────────────────────────────────────────────────────────────────


class EditParams(msgspec.Struct, kw_only=True):
    path: str
    old: Annotated[str, msgspec.Meta(min_length=1, description="Exact text to find")]
    new: Annotated[str, msgspec.Meta(description="Text to put in its place")]
    count: Annotated[int, msgspec.Meta(ge=1, description="How many occurrences there must be; all are replaced")] = 1


class FsEdit(Capability):
    name = "fs.edit"
    summary = "Replace exact text in a text file. Fails unless the text occurs exactly `count` times."
    Params = EditParams

    def effects(self, p: EditParams, env: Env) -> Effects:
        return LOCAL_UNDOABLE

    def resources(self, p: EditParams, env: Env) -> list[Resource]:
        return write_resource(env, p.path, "path")

    def describe(self, p: EditParams, env: Env) -> str:
        return f"Edit {p.path}: replace {p.count} occurrence{'s' if p.count != 1 else ''} of “{_clip(p.old)}”"

    async def run(self, p: EditParams, ctx: ActionContext) -> ActionResult:
        env = ctx.env
        path = judged_path(ctx, "path", resolve_existing(env, p.path, want_dir=False))
        with folder(env, path.parent) as parent:
            file_fd = open_file(env, parent.fd, path.name, path)
            with os.fdopen(file_fd, "rb") as f:
                text = f.read().decode("utf-8")
                found = text.count(p.old)
                if found != p.count:
                    raise CapabilityError("invalid", f"the text occurs {found} time{'s' if found != 1 else ''} in "
                                                     f"{env.show(path)}, not {p.count}")
                saved = backup(ctx, f.fileno(), path.name)  # exactly what was read, for undo
                mode = os.fstat(f.fileno())
            write_atomic(parent.fd, path.name, text.replace(p.old, p.new).encode(), ctx.action_id, replace=True,
                         mode_of=mode)
        return ActionResult(ok=True, observation=f"Edited {env.show(path)} ({found} replacement{'s' if found != 1 else ''})",
                            summary=f"Edited {env.show(path)}", undo={"kind": "edit", "path": str(path), "backup": saved})

    async def verify(self, p: EditParams, result: ActionResult, ctx: ActionContext) -> CheckResult:
        saved = Path((result.undo or {}).get("backup", ""))
        path = target(ctx.env, p.path)
        expected = saved.read_text(encoding="utf-8").replace(p.old, p.new) if saved.is_file() else None
        ok = expected is not None and path.is_file() and path.read_text(encoding="utf-8") == expected
        return CheckResult(status="passed" if ok else "failed")

    async def probe(self, p: EditParams, ctx: ActionContext) -> Disposition:
        path = target(ctx.env, p.path)
        _clean_temp(path, ctx.action_id)
        saved = ctx.backup_dir / path.name
        if not saved.is_file() or not path.is_file():
            return Disposition.NONE if path.is_file() else Disposition.UNKNOWN
        current, before = path.read_text(encoding="utf-8"), saved.read_text(encoding="utf-8")
        if current == before.replace(p.old, p.new):
            return Disposition.CONFIRMED
        return Disposition.NONE if current == before else Disposition.UNKNOWN


# ── fs.move ─────────────────────────────────────────────────────────────────


class MoveParams(msgspec.Struct, kw_only=True):
    source: str
    destination: Annotated[str, msgspec.Meta(
        description="New path, or a folder to move into (an existing one, or end it with /); "
                    "missing folders are created")]


class FsMove(Capability):
    name = "fs.move"
    summary = "Move or rename a file or folder. Never replaces an existing file."
    Params = MoveParams
    timeout_s = 120.0

    def effects(self, p: MoveParams, env: Env) -> Effects:
        return LOCAL_UNDOABLE

    def resources(self, p: MoveParams, env: Env) -> list[Resource]:
        source, dest = self._paths(p, env)
        return [Resource(kind="path", value=str(source), access="write", role="source"),
                Resource(kind="path", value=str(dest), access="write", role="destination")]

    def describe(self, p: MoveParams, env: Env) -> str:
        return f"Move {p.source} to {p.destination}"

    def _paths(self, p: MoveParams, env: Env) -> tuple[Path, Path]:
        source = target(env, p.source)
        dest = target(env, p.destination)
        # Into a folder: one that exists, or one written with a trailing slash ("Invoices/2026/").
        if p.destination.rstrip().endswith("/") or (dest.is_dir() and dest != source):
            dest = dest / source.name
        return source, dest

    async def run(self, p: MoveParams, ctx: ActionContext) -> ActionResult:
        env = ctx.env
        source = judged_path(ctx, "source", resolve_existing(env, p.source), follow=False)
        dest = judged_path(ctx, "destination", self._paths(p, env)[1])
        if dest == source:
            raise CapabilityError("invalid", f"{env.show(source)} is already there")
        exists = CapabilityError("exists", f"{env.show(dest)} already exists; choose another name")
        if dest.exists() or dest.is_symlink():
            raise exists
        if source in dest.parents:
            raise CapabilityError("invalid", "a folder can't be moved into itself")
        with folder(env, source.parent) as src:
            if entry(src.fd, source.name) is None:
                raise CapabilityError("not_found", f"{env.show(source)} doesn't exist")
            with folder(env, dest.parent, create=True) as dst:
                try:
                    move_at(src, source.name, dst, dest.name)
                except FileExistsError:
                    raise exists from None
                created = dst.created
        return ActionResult(ok=True, observation=f"Moved {env.show(source)} to {env.show(dest)}",
                            summary=f"Moved {source.name} to {env.show(dest.parent)}",
                            undo={"kind": "move", "from": str(dest), "to": str(source), "created_dirs": created})

    async def verify(self, p: MoveParams, result: ActionResult, ctx: ActionContext) -> CheckResult:
        dest = Path((result.undo or {})["from"])
        source = Path((result.undo or {})["to"])
        ok = dest.exists() and not source.exists()
        return CheckResult(status="passed" if ok else "failed")

    async def probe(self, p: MoveParams, ctx: ActionContext) -> Disposition:
        source, dest = target(ctx.env, p.source), target(ctx.env, p.destination)
        candidates = [dest, dest / source.name]
        moved = any(c.exists() for c in candidates)
        if moved and not source.exists():
            return Disposition.CONFIRMED
        if source.exists() and not moved:
            return Disposition.NONE
        return Disposition.UNKNOWN  # both or neither: a copy across drives stopped part way


# ── fs.make_dir ─────────────────────────────────────────────────────────────


class MakeDirParams(msgspec.Struct, kw_only=True):
    path: str


class FsMakeDir(Capability):
    name = "fs.make_dir"
    summary = "Create a folder, and any missing folders above it."
    Params = MakeDirParams
    idempotent = True

    def effects(self, p: MakeDirParams, env: Env) -> Effects:
        return LOCAL_UNDOABLE

    def resources(self, p: MakeDirParams, env: Env) -> list[Resource]:
        return write_resource(env, p.path, "path")

    def describe(self, p: MakeDirParams, env: Env) -> str:
        return f"Create the folder {p.path}"

    async def run(self, p: MakeDirParams, ctx: ActionContext) -> ActionResult:
        env = ctx.env
        path = judged_path(ctx, "path", target(env, p.path))
        if path.exists() and not path.is_dir():
            raise CapabilityError("exists", f"{env.show(path)} exists and is not a folder")
        with folder(env, path, create=True) as made:
            created = made.created
        if not created:
            return ActionResult(ok=True, observation=f"{env.show(path)} already exists", summary=f"{env.show(path)} exists",
                                undo={"kind": "make_dir", "created": []})
        return ActionResult(ok=True, observation=f"Created {env.show(path)}", summary=f"Created {env.show(path)}",
                            undo={"kind": "make_dir", "created": created})

    async def verify(self, p: MakeDirParams, result: ActionResult, ctx: ActionContext) -> CheckResult:
        return CheckResult(status="passed" if target(ctx.env, p.path).is_dir() else "failed")


# ── fs.trash ────────────────────────────────────────────────────────────────


class TrashParams(msgspec.Struct, kw_only=True):
    path: str


class FsTrash(Capability):
    name = "fs.trash"
    summary = "Move a file or folder to the trash, where it can be restored."
    Params = TrashParams

    def effects(self, p: TrashParams, env: Env) -> Effects:
        return LOCAL_UNDOABLE

    def resources(self, p: TrashParams, env: Env) -> list[Resource]:
        return write_resource(env, p.path, "path")

    def describe(self, p: TrashParams, env: Env) -> str:
        return f"Move {p.path} to the trash"

    async def run(self, p: TrashParams, ctx: ActionContext) -> ActionResult:
        env = ctx.env
        path = judged_path(ctx, "path", resolve_existing(env, p.path), follow=False)
        trashed, info = trash(env, path)
        return ActionResult(ok=True, observation=f"Moved {env.show(path)} to the trash",
                            summary=f"Trashed {path.name}",
                            undo={"kind": "trash", "trashed": str(trashed), "info": str(info), "original": str(path)})

    async def verify(self, p: TrashParams, result: ActionResult, ctx: ActionContext) -> CheckResult:
        undo = result.undo or {}
        ok = Path(undo["trashed"]).exists() and not Path(undo["original"]).exists()
        return CheckResult(status="passed" if ok else "failed")

    async def probe(self, p: TrashParams, ctx: ActionContext) -> Disposition:
        path = target(ctx.env, p.path)
        entry = find_trashed(ctx.env, path)
        if entry is not None and not path.exists():
            return Disposition.CONFIRMED
        return Disposition.NONE if path.exists() else Disposition.UNKNOWN


def trash(env: Env, path: Path) -> tuple[Path, Path]:
    """Move `path` (judged, without links) into the home trash (freedesktop Trash spec 1.0) and
    return (file, info). The item, the trash's `files`, and its `info` are each reached through a
    held folder."""
    root = Path(os.path.realpath(env.trash_dir))
    stamp = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with folder(env, path.parent) as src, folder(env, root / "files", create=True, mode=0o700) as files, \
            folder(env, root / "info", create=True, mode=0o700) as info:
        item = entry(src.fd, path.name)
        if item is None:
            raise CapabilityError("not_found", f"{env.show(path)} doesn't exist")
        if item.st_dev != os.fstat(files.fd).st_dev:
            raise CapabilityError("unavailable", f"{env.show(path)} is on another drive; Mei can only trash files on "
                                                 "the drive that holds your home folder")
        for n in range(1, 10_000):
            name = path.name if n == 1 else _numbered(path.name, n)
            record = f"{name}.trashinfo"
            try:
                fd = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600,
                             dir_fd=info.fd)
            except FileExistsError:
                continue
            with os.fdopen(fd, "w") as f:
                f.write(f"[Trash Info]\nPath={quote(str(path))}\nDeletionDate={stamp}\n")
            try:
                rename_noreplace(src.fd, path.name, files.fd, name)
            except FileExistsError:
                os.unlink(record, dir_fd=info.fd)
                continue
            except OSError:
                os.unlink(record, dir_fd=info.fd)
                raise
            return root / "files" / name, root / "info" / record
    raise CapabilityError("failed", "couldn't find a free name in the trash")


def find_trashed(env: Env, original: Path) -> Path | None:
    info = env.trash_dir / "info"
    if not info.is_dir():
        return None
    for entry in sorted(info.glob("*.trashinfo"), key=lambda e: e.stat().st_mtime, reverse=True):
        for line in entry.read_text(errors="replace").splitlines():
            if line.startswith("Path=") and unquote(line[5:]) == str(original):
                return env.trash_dir / "files" / entry.name.removesuffix(".trashinfo")
    return None


def _numbered(name: str, n: int) -> str:
    stem, dot, ext = name.rpartition(".")
    return f"{stem}.{n}.{ext}" if dot and stem else f"{name}.{n}"


def _clip(text: str, width: int = 40) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= width else one_line[:width - 1] + "…"
