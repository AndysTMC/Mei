"""PDF text through poppler's `pdftotext`, inside a bubblewrap jail when one is available.

PDFs come from anywhere and their parsers are a classic way in, so the parser sees only the one
file (read-only), no network, no home folder, and dies with Mei (§5.4). It gets the file Mei
opened, by its descriptor, not by a path that a link could redirect (decision 0015).
"""

import logging
import os

from .run import ToolFailed, checked

log = logging.getLogger("mei.desktop")
PDFTOTEXT = "/usr/bin/pdftotext"
BWRAP = "/usr/bin/bwrap"
MAX_PAGES = 100
TIMEOUT_S = 30.0


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
        if self._bwrap is None:
            argv = [self._tool, *args, f"/proc/self/fd/{file_fd}", "-"]  # the child's own copy of the fd
        else:
            argv = [self._bwrap, "--unshare-all", "--die-with-parent", "--new-session", "--clearenv",
                    "--ro-bind", "/usr", "/usr", "--ro-bind-try", "/lib", "/lib", "--ro-bind-try", "/lib64", "/lib64",
                    "--ro-bind-try", "/bin", "/bin", "--ro-bind-try", "/etc/fonts", "/etc/fonts",
                    "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
                    "--ro-bind-fd", str(file_fd), "/tmp/in.pdf", self._tool, *args, "/tmp/in.pdf", "-"]
        try:
            text = await checked(argv, timeout=TIMEOUT_S, max_output=max_chars * 4, pass_fds=(file_fd,))
        except TimeoutError:
            raise ToolFailed(f"reading the PDF took longer than {int(TIMEOUT_S)} s") from None
        return text.replace("\x0c", "\n")[:max_chars]  # pdftotext ends each page with a form feed
