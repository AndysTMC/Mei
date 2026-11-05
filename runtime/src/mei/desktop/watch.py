"""Watching the folders a command can see for secret files that appear while it runs (decision 0016).

Secrets inside a folder are masked when the command starts (`Paths.secrets_under`), but a file
written there afterwards (a `.env` saved by the person's editor, a key dropped in by a download)
would be visible. inotify reports each new name in the watched folders; when one is a name Mei
hides, `tripped` is set and the runner stops the command and keeps its output from the model.

Folders are watched through the descriptors the run holds (`/proc/self/fd/N`), so a link swapped
in can't point the watch elsewhere. Folders made during the run are added, and their contents
checked at once, since files can land in them before the watch does.
"""

import asyncio
import ctypes
import errno
import logging
import os
import struct
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("mei.desktop")

MAX_FOLDERS = 4096  # inotify watches cost kernel memory; past this, the run says it couldn't watch everything
_IN_MOVED_TO, _IN_CREATE, _IN_Q_OVERFLOW = 0x80, 0x100, 0x4000
_IN_ONLYDIR, _IN_DONT_FOLLOW, _IN_ISDIR = 0x01000000, 0x02000000, 0x40000000
_EVENT = struct.Struct("iIII")  # wd, mask, cookie, len; then the name, NUL-padded

_libc = ctypes.CDLL(None, use_errno=True)


class SecretWatch:
    def __init__(self, folders: list[tuple[Path, int]], secret: Callable[[Path], bool],
                 masked: frozenset[Path] = frozenset()) -> None:
        """`folders`: each folder's judged path and the descriptor holding it open. `masked`: the
        secrets the command won't see; any other already there landed after they were looked for."""
        self._secret = secret
        self._masked = masked
        self._dirs: dict[int, Path] = {}  # watch → the folder's judged path (what a secret is judged by)
        self._reach: dict[int, str] = {}  # watch → how to reach it: through the held descriptor
        self._loop: asyncio.AbstractEventLoop | None = None
        self.tripped = asyncio.Event()
        self.found: Path | None = None  # the secret that appeared (or a folder whose changes were lost)
        self.complete = True
        self._fd = _libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self._fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")
        for path, fd in folders:  # watched before the command starts, then what is there is checked
            self._add_tree(f"/proc/self/fd/{fd}", path, new=False)

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._loop.add_reader(self._fd, self._read)

    def drain(self) -> None:
        """Take in what inotify has queued now (the command may have ended before it was read)."""
        while self._fd >= 0 and self._read():
            pass

    def close(self) -> None:
        if self._loop is not None:
            self._loop.remove_reader(self._fd)
            self._loop = None
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def _add_tree(self, real: str, shown: Path, *, new: bool) -> None:
        """Watch a folder and those below it. In a folder `new` to the run, anything secret already
        inside trips the watch (it landed before the watch did)."""
        for here, dirs, files in os.walk(real):  # links aren't followed into
            rel = os.path.relpath(here, real)
            base = shown if rel == "." else shown / rel
            if not self._add(here, base, root=here == real):
                return
            for name in [*dirs, *files]:
                if new or base / name not in self._masked:
                    self._check(base / name)
            dirs[:] = [d for d in dirs if not self._secret(base / d)]

    def _add(self, real: str, shown: Path, *, root: bool) -> bool:
        if len(self._dirs) >= MAX_FOLDERS:
            self.complete = False
            return False
        # A held folder is reached through its /proc/self/fd link, which must be followed; below it,
        # a folder replaced by a link is never followed.
        mask = _IN_CREATE | _IN_MOVED_TO | _IN_ONLYDIR | (0 if root and real.startswith("/proc/self/fd/") else _IN_DONT_FOLLOW)
        wd = _libc.inotify_add_watch(self._fd, os.fsencode(real), mask)
        if wd < 0:
            err = ctypes.get_errno()
            if not (err == errno.ENOENT or (err == errno.ENOTDIR and not root)):  # gone, or now a link: skip it
                log.warning("couldn't watch %s: %s", shown, os.strerror(err))
                self.complete = False
            return True
        self._dirs[wd] = shown
        self._reach[wd] = real
        return True

    def _check(self, path: Path) -> None:
        if self.found is None and self._secret(path):
            self.found = path
            self.tripped.set()

    def _read(self) -> bool:
        """Handle one read's worth of events; False when there was nothing to read."""
        try:
            data = os.read(self._fd, 65536)
        except BlockingIOError:
            return False
        offset = 0
        while offset + _EVENT.size <= len(data):
            wd, mask, _cookie, length = _EVENT.unpack_from(data, offset)
            name = data[offset + _EVENT.size: offset + _EVENT.size + length].rstrip(b"\0").decode("utf-8", "surrogateescape")
            offset += _EVENT.size + length
            if mask & _IN_Q_OVERFLOW:  # events were dropped: a secret could be among them
                self.found = self.found or next(iter(self._dirs.values()), Path("/"))
                self.tripped.set()
                continue
            base = self._dirs.get(wd)
            if base is None or not name:
                continue
            path = base / name
            self._check(path)
            if mask & _IN_ISDIR and not self._secret(path):
                # A folder made during the run: watch it, and look at what may already be inside.
                self._add_tree(os.path.join(self._reach[wd], name), path, new=True)
        return True
