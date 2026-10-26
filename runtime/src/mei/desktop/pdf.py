"""PDFs through poppler: their text with `pdftotext` (for the model), and their pages as pictures
with `pdfinfo` and `pdftoppm` (for the popup's viewer, decision 0029). Each runs inside a bubblewrap
jail when one is available.

PDFs come from anywhere and their parsers are a classic way in, so the parser sees only the one
file (read-only), no network, no home folder, and dies with Mei (§5.4). It gets the file Mei
opened, by its descriptor, not by a path that a link could redirect (decision 0015).
"""

import contextlib
import hashlib
import logging
import os
import re
import stat
from pathlib import Path

from .run import ToolFailed, checked, checked_bytes

log = logging.getLogger("mei.desktop")
PDFTOTEXT = "/usr/bin/pdftotext"
PDFTOPPM = "/usr/bin/pdftoppm"
PDFINFO = "/usr/bin/pdfinfo"
BWRAP = "/usr/bin/bwrap"
MAX_PAGES = 100
TIMEOUT_S = 30.0
MAX_PAGE_PNG = 24 * 1024 * 1024
MIN_PAGE_WIDTH, MAX_PAGE_WIDTH = 100, 2400
MAX_CACHED_PAGES = 200  # drawn pages kept for scrolling back; the oldest go first


class PdfToText:
    def __init__(self, tool: str = PDFTOTEXT, bwrap: str = BWRAP) -> None:
        self._tool = tool
        self._bwrap = bwrap if os.access(bwrap, os.X_OK) else None
        if self._bwrap is None:
            log.warning("bubblewrap isn't installed: PDFs will be read without a sandbox")

    @staticmethod
    def available(tool: str = PDFTOTEXT) -> bool:
        return os.access(tool, os.X_OK)

    async def pdf_text(self, file_fd: int, max_chars: int) -> str:
        args = ["-layout", "-enc", "UTF-8", "-l", str(MAX_PAGES)]
        argv = _jailed(self._bwrap, self._tool, args, file_fd, ["-"])
        try:
            text = await checked(argv, timeout=TIMEOUT_S, max_output=max_chars * 4, pass_fds=(file_fd,))
        except TimeoutError:
            raise ToolFailed(f"reading the PDF took longer than {int(TIMEOUT_S)} s") from None
        return text.replace("\x0c", "\n")[:max_chars]  # pdftotext ends each page with a form feed


class PdfPages:
    """A PDF's page count, and one page at a time as a PNG of the width asked for. Drawn pages are kept
    in `cache` (the runtime dir: gone at logout), keyed by the file's identity and change time."""

    def __init__(self, cache: Path, tool: str = PDFTOPPM, info: str = PDFINFO, bwrap: str = BWRAP) -> None:
        self._cache = cache
        self._tool = tool
        self._info = info
        self._bwrap = bwrap if os.access(bwrap, os.X_OK) else None

    @staticmethod
    def available(tool: str = PDFTOPPM, info: str = PDFINFO) -> bool:
        return os.access(tool, os.X_OK) and os.access(info, os.X_OK)

    async def pages(self, path: str) -> int:
        fd = _open_file(path)
        try:
            out = await checked(_jailed(self._bwrap, self._info, [], fd, []), timeout=TIMEOUT_S, pass_fds=(fd,))
        except TimeoutError:
            raise ToolFailed(f"reading the PDF took longer than {int(TIMEOUT_S)} s") from None
        finally:
            os.close(fd)
        found = re.search(r"^Pages:\s+(\d+)\s*$", out, re.MULTILINE)
        if found is None:
            raise ToolFailed("pdfinfo didn't say how many pages it has")
        return int(found.group(1))

    async def page(self, path: str, page: int, width: int) -> Path:
        """Page `page` (from 1) drawn `width` pixels wide: the cached PNG's path."""
        width = max(MIN_PAGE_WIDTH, min(MAX_PAGE_WIDTH, width))
        fd = _open_file(path)
        try:
            info = os.fstat(fd)
            key = hashlib.sha256(f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}".encode()).hexdigest()
            out = self._cache / f"{key[:32]}-{page}-{width}.png"
            if out.exists():
                return out
            args = ["-png", "-f", str(page), "-l", str(page), "-singlefile", "-scale-to-x", str(width), "-scale-to-y", "-1"]
            try:
                png = await checked_bytes(_jailed(self._bwrap, self._tool, args, fd, []), timeout=TIMEOUT_S,
                                          max_output=MAX_PAGE_PNG, pass_fds=(fd,))
            except TimeoutError:
                raise ToolFailed(f"drawing the page took longer than {int(TIMEOUT_S)} s") from None
        finally:
            os.close(fd)
        if not png.startswith(b"\x89PNG"):
            raise ToolFailed(f"pdftoppm drew no page {page}")
        self._cache.mkdir(mode=0o700, parents=True, exist_ok=True)
        part = out.with_suffix(".part")
        part.write_bytes(png)
        part.replace(out)  # whole or not at all: the Shell may be reading the folder
        self._prune()
        return out

    def _prune(self) -> None:
        drawn = sorted(self._cache.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in drawn[MAX_CACHED_PAGES:]:
            with contextlib.suppress(OSError):
                old.unlink()


def _open_file(path: str) -> int:
    """The file the Shell named, opened once; its tools get this descriptor, not the path."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK)
    except OSError as e:
        raise FileNotFoundError(f"couldn't open {os.path.basename(path)}: {e.strerror}") from None
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise FileNotFoundError(f"{os.path.basename(path)} isn't a file")
    return fd


def _jailed(bwrap: str | None, tool: str, args: list[str], file_fd: int, after: list[str]) -> list[str]:
    """`tool args <the file> after`, in a jail that sees only /usr, fonts and that one file, read-only."""
    if bwrap is None:
        return [tool, *args, f"/proc/self/fd/{file_fd}", *after]  # the child's own copy of the fd
    return [bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
            "--ro-bind", "/usr", "/usr", "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64",
            "--ro-bind-try", "/bin", "/bin", "--ro-bind-try", "/etc/fonts", "/etc/fonts",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--ro-bind-fd", str(file_fd), "/tmp/in.pdf", tool, *args, "/tmp/in.pdf", *after]
