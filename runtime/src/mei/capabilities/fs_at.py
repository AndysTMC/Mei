"""File operations that change what policy judged, not wherever a link leads by the time they run
(decision 0014).

Policy judges an action's paths by where they really lead and checks them again just before the
run (decision 0010). Something else on the machine could still swap a folder on the way for a link
after that check, and a path-based write would follow it. So the run takes the judged path (it
has no links in it: it was resolved), checks the path it was given still leads there, then walks
it from `/` one folder at a time with `O_NOFOLLOW` and holds the last folder open. A link anywhere
on the way stops the walk. Everything after acts relative to the held folder, which no later swap
can redirect, and never follows a link in the last component either.
"""

import ctypes
import errno
import os
import shutil
import stat
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path

from .base import ActionContext, CapabilityError, Env

_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_NEW = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
_RENAME_NOREPLACE = 1
_CHUNK = 1 << 20


def changed(env: Env, path: Path) -> CapabilityError:
    return CapabilityError("changed", f"{env.show(path)} changed since Mei checked it (a folder on the way is now a "
                                      "link), so Mei didn't touch it")


def judged_path(ctx: ActionContext, role: str, given: Path, *, follow: bool = True, index: int = 0) -> Path:
    """Where this action may act for `role` (its `index`-th resource with that role). The path the
    run was given must still lead where policy judged it does (policy follows every link, the last
    one too); if it leads elsewhere now, something changed after the check.

    With `follow`, that judged path is where it acts. Without it (moving or trashing an item, which
    acts on a link itself, not on what it points to), it acts on the item at the end of the given
    path, reached through its folder's link-free path."""
    real = Path(os.path.realpath(given))
    values = ctx.judged.get(role, ())
    judged = values[index] if index < len(values) else None
    if role in ctx.judged and (judged is None or Path(judged) != real):
        raise changed(ctx.env, given)
    if not follow:
        return Path(os.path.realpath(given.parent)) / given.name
    return Path(judged) if judged is not None else real


@dataclass
class Folder:
    fd: int
    path: Path
    created: list[str] = field(default_factory=list)  # folders the walk made, outermost first (for undo)


@contextmanager
def folder(env: Env, path: Path, *, create: bool = False, mode: int = 0o777) -> Iterator[Folder]:
    """Hold the folder at `path` (absolute, without links) open, reached without following any link.
    With `create`, missing folders are made on the way."""
    opened = _walk(env, path, create, mode)
    try:
        yield opened
    finally:
        os.close(opened.fd)


def _walk(env: Env, path: Path, create: bool, mode: int) -> Folder:
    if not path.is_absolute():
        raise ValueError(f"{path} isn't absolute")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    held = Folder(fd, path)
    here = Path("/")
    try:
        for part in path.parts[1:]:
            here = here / part
            held.fd = _step(env, held, part, here, create, mode)
        return held
    except BaseException:
        os.close(held.fd)
        raise


def _step(env: Env, held: Folder, part: str, here: Path, create: bool, mode: int) -> int:
    """Open `part` inside the held folder, closing the held one. Returns the new folder's fd."""
    try:
        try:
            nxt = os.open(part, _DIR, dir_fd=held.fd)
        except FileNotFoundError:
            if not create:
                raise CapabilityError("not_found", f"{env.show(here)} doesn't exist") from None
            try:
                os.mkdir(part, mode, dir_fd=held.fd)
                held.created.append(str(here))
            except FileExistsError:
                pass  # made meanwhile; opening it says whether it is a folder
            nxt = os.open(part, _DIR, dir_fd=held.fd)
    except NotADirectoryError:
        raise _not_a_folder(env, held.fd, part, here) from None
    except PermissionError:
        raise CapabilityError("permission", f"Mei isn't allowed into {env.show(here)}") from None
    os.close(held.fd)
    return nxt


def _not_a_folder(env: Env, dir_fd: int, name: str, here: Path) -> CapabilityError:
    if stat.S_ISLNK(os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode):
        return changed(env, here)
    return CapabilityError("invalid", f"{env.show(here)} exists and is not a folder")


def entry(dir_fd: int, name: str) -> os.stat_result | None:
    """What is at `name` in the folder, itself and not what it links to; None if nothing is."""
    try:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def open_file(env: Env, dir_fd: int, name: str, path: Path) -> int:
    """Open a regular file for reading, never through a link."""
    try:
        fd = os.open(name, _FILE, dir_fd=dir_fd)
    except FileNotFoundError:
        raise CapabilityError("not_found", f"{env.show(path)} doesn't exist") from None
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise changed(env, path) from None
        raise
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise CapabilityError("invalid", f"{env.show(path)} is not a regular file")
    return fd


def look(env: Env, path: Path, *, follow: bool = True) -> os.stat_result | None:
    """What is at `path` now, for a check or a probe: None if nothing is. The folders on the way are
    walked without following links, from where they really lead now. With `follow`, the item is
    where `path` leads; without, it is the item at the end of `path` itself (a link stays a link).
    A link swapped in during the look raises `changed`, so a check can say it couldn't tell."""
    where = Path(os.path.realpath(path if follow else path.parent))
    target = where if follow else where / path.name
    try:
        with folder(env, target.parent) as held:
            st = entry(held.fd, target.name)
    except CapabilityError as e:
        if e.error_class == "not_found":
            return None
        raise
    if follow and st is not None and stat.S_ISLNK(st.st_mode):
        raise changed(env, path)
    return st


def names(env: Env, path: Path) -> list[str]:
    """The entries of the folder `path` leads to, read from the folder held open."""
    with folder(env, Path(os.path.realpath(path))) as held:
        return os.listdir(held.fd)


@contextmanager
def held_file(env: Env, path: Path) -> Iterator[int]:
    """The regular file at `path` (absolute, without links) open for reading, reached through its held
    folder and never through a link."""
    with folder(env, path.parent) as parent:
        fd = open_file(env, parent.fd, path.name, path)
    try:
        yield fd
    finally:
        os.close(fd)


def backup(ctx: ActionContext, file_fd: int, name: str) -> str:
    """Copy the open file into this action's backups, with its mode and times; returns where."""
    ctx.backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    copy = ctx.backup_dir / name
    st = os.fstat(file_fd)
    os.lseek(file_fd, 0, os.SEEK_SET)
    with open(copy, "wb") as out:
        while chunk := os.read(file_fd, _CHUNK):
            out.write(chunk)
    os.chmod(copy, stat.S_IMODE(st.st_mode))
    os.utime(copy, ns=(st.st_atime_ns, st.st_mtime_ns))
    return str(copy)


def write_atomic(dir_fd: int, name: str, data: bytes, action_id: str, *, replace: bool,
                 mode_of: os.stat_result | None = None) -> None:
    """Write `data` to `name` in the folder in one step: a temp file renamed into place. Without
    `replace`, an existing file is never replaced (FileExistsError)."""
    temp = temp_name(action_id)
    fd = os.open(temp, _NEW, 0o666, dir_fd=dir_fd)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            if mode_of is not None:
                os.fchmod(f.fileno(), stat.S_IMODE(mode_of.st_mode))
        if replace:
            os.replace(temp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        else:
            rename_noreplace(dir_fd, temp, dir_fd, name)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temp, dir_fd=dir_fd)
        raise


def temp_name(action_id: str) -> str:
    return f".mei-tmp-{action_id}"


def rename_noreplace(src_fd: int, src: str, dst_fd: int, dst: str) -> None:
    """Rename within or between held folders, failing with FileExistsError rather than replacing
    what is at `dst`. Neither name is followed if it is a link."""
    result = _renameat2(src_fd, os.fsencode(src), dst_fd, os.fsencode(dst), _RENAME_NOREPLACE) if _renameat2 else -1
    if result == 0:
        return
    err = ctypes.get_errno() if _renameat2 else errno.ENOSYS
    if err not in (errno.EINVAL, errno.ENOSYS):  # EINVAL: this file system can't promise "no replace"
        raise OSError(err, os.strerror(err), dst)
    if entry(dst_fd, dst) is not None:  # checked, then renamed: a narrow window only such file systems have
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), dst)
    os.rename(src, dst, src_dir_fd=src_fd, dst_dir_fd=dst_fd)


def _load_renameat2():
    try:
        fn = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError):
        return None  # glibc before 2.28, or another libc without it
    fn.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    fn.restype = ctypes.c_int
    return fn


_renameat2 = _load_renameat2()


def move_at(src: Folder, name: str, dst: Folder, new_name: str) -> None:
    """Move `name` out of one held folder into another as `new_name`, never replacing anything there.
    Across drives it is copied and then removed, still through the held folders."""
    try:
        rename_noreplace(src.fd, name, dst.fd, new_name)
        return
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
    st = entry(src.fd, name)
    if st is None:
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), name)
    if stat.S_ISDIR(st.st_mode):
        # /proc/self/fd/N is the held folder itself, whatever its path has become since. copytree
        # makes the new folder itself, so it fails rather than merge into one that appeared.
        shutil.copytree(f"/proc/self/fd/{src.fd}/{name}", f"/proc/self/fd/{dst.fd}/{new_name}", symlinks=True)
        shutil.rmtree(name, dir_fd=src.fd)
    elif stat.S_ISLNK(st.st_mode):
        os.symlink(os.readlink(name, dir_fd=src.fd), new_name, dir_fd=dst.fd)
        os.unlink(name, dir_fd=src.fd)
    elif stat.S_ISREG(st.st_mode):
        _copy_file(src.fd, name, dst.fd, new_name)
        os.unlink(name, dir_fd=src.fd)
    else:
        raise OSError(errno.EINVAL, "only files, folders, and links can be moved to another drive", name)


def _copy_file(src_fd: int, name: str, dst_fd: int, new_name: str) -> None:
    """Copy a file between held folders, with its mode and times; never replaces what is at `new_name`."""
    with os.fdopen(os.open(name, _FILE, dir_fd=src_fd), "rb") as source:
        st = os.fstat(source.fileno())
        out = os.open(new_name, _NEW, 0o600, dir_fd=dst_fd)
        try:
            with os.fdopen(out, "wb") as target:
                shutil.copyfileobj(source, target, _CHUNK)
                os.fchmod(target.fileno(), stat.S_IMODE(st.st_mode))
                os.utime(target.fileno(), ns=(st.st_atime_ns, st.st_mtime_ns))
        except BaseException:
            os.unlink(new_name, dir_fd=dst_fd)
            raise
