"""Reading the file system: list, search, read (§9.3). Nothing here changes anything.

File names and contents are written by whoever made the file, so every observation here is
untrusted (§13.4): the model sees it wrapped as data, and paths taken from it count as untrusted.
"""

import datetime
import fnmatch
import os
import stat
from pathlib import Path
from typing import Annotated

import msgspec

from .base import ActionContext, ActionResult, Capability, CapabilityError, Env, Resource

MAX_LIST = 1000
MAX_SCAN = 20_000  # entries a search looks at before it stops and says so
MAX_TEXT_SEARCH_BYTES = 2 * 1024 * 1024
MAX_READ_CHARS = 100_000
TEXT_SUFFIXES_NOT_READABLE = (".zip", ".gz", ".xz", ".zst", ".tar", ".7z", ".iso", ".png", ".jpg", ".jpeg", ".gif",
                              ".webp", ".mp3", ".mp4", ".mkv", ".ogg", ".flac", ".odt", ".docx", ".xlsx", ".pptx")


def describe_size(size: int) -> str:
    value, unit = float(size), "B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            break
        value /= 1000
    return f"{int(value)} {unit}" if unit == "B" or value >= 10 else f"{value:.1f} {unit}"


def local_time(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def parse_when(value: str, field: str) -> float | None:
    """`2026-10-14` or `2026-10-14T09:30` in local time; empty means no bound."""
    if not value.strip():
        return None
    try:
        when = datetime.datetime.fromisoformat(value.strip())
    except ValueError:
        raise CapabilityError("invalid", f"{field} must be a date like 2026-10-14 (got {value!r})") from None
    if when.tzinfo is None:
        when = when.astimezone()  # local time, as people mean it
    return when.timestamp()


def resolve_existing(env: Env, value: str, *, want_dir: bool | None = None) -> Path:
    try:
        path = env.path(value)
    except ValueError as e:
        raise CapabilityError("invalid", str(e)) from None
    if not path.exists():
        raise CapabilityError("not_found", f"{env.show(path)} doesn't exist")
    if want_dir is True and not path.is_dir():
        raise CapabilityError("invalid", f"{env.show(path)} is not a folder")
    if want_dir is False and path.is_dir():
        raise CapabilityError("invalid", f"{env.show(path)} is a folder")
    return path


def entry_line(env: Env, path: Path, st: os.stat_result, *, full: bool) -> str:
    name = env.show(path) if full else path.name
    if stat.S_ISDIR(st.st_mode):
        return f"- {name}/ (folder, modified {local_time(st.st_mtime)})"
    return f"- {name} ({describe_size(st.st_size)}, modified {local_time(st.st_mtime)})"


def _read_resource(env: Env, value: str) -> list[Resource]:
    try:
        path = env.path(value)
    except ValueError as e:
        raise CapabilityError("invalid", str(e)) from None
    return [Resource(kind="path", value=str(path), access="read", role="path")]


# ── fs.list ─────────────────────────────────────────────────────────────────


class ListParams(msgspec.Struct, kw_only=True):
    path: Annotated[str, msgspec.Meta(description="Folder to list, e.g. ~/Downloads")]
    pattern: Annotated[str, msgspec.Meta(description="Only names matching this glob, e.g. *.pdf")] = "*"
    include_hidden: bool = False
    limit: Annotated[int, msgspec.Meta(ge=1, le=MAX_LIST)] = 200


class FsList(Capability):
    name = "fs.list"
    summary = "List the files and folders in one folder, with sizes and modification times."
    Params = ListParams
    idempotent = True

    def resources(self, p: ListParams, env: Env) -> list[Resource]:
        return _read_resource(env, p.path)

    def describe(self, p: ListParams, env: Env) -> str:
        return f"List {p.path}"

    async def run(self, p: ListParams, ctx: ActionContext) -> ActionResult:
        env = ctx.env
        folder = resolve_existing(env, p.path, want_dir=True)
        rows: list[tuple[Path, os.stat_result]] = []
        try:
            names = sorted(os.listdir(folder), key=str.lower)
        except PermissionError:
            raise CapabilityError("permission", f"no permission to list {env.show(folder)}") from None
        for name in names:
            if not p.include_hidden and name.startswith("."):
                continue
            if not fnmatch.fnmatch(name.lower(), p.pattern.lower()):
                continue
            try:
                rows.append((folder / name, os.lstat(folder / name)))
            except OSError:
                continue  # removed while we listed
        shown = rows[:p.limit]
        head = f"{env.show(folder)}: {len(rows)} entries" + (f", showing the first {p.limit}" if len(rows) > p.limit else "")
        body = "\n".join(entry_line(env, path, st, full=False) for path, st in shown)
        return ActionResult(ok=True, observation=f"{head}\n{body}" if body else f"{head} (empty)",
                            summary=f"Listed {env.show(folder)} ({len(rows)} entries)", trust="untrusted")


# ── fs.search ───────────────────────────────────────────────────────────────


class SearchParams(msgspec.Struct, kw_only=True):
    path: Annotated[str, msgspec.Meta(description="Folder to search in, recursively")] = "~"
    name: Annotated[str, msgspec.Meta(description="Glob the file name must match, e.g. *invoice*.pdf")] = "*"
    text: Annotated[str, msgspec.Meta(description="Text the file must contain (plain-text files only)")] = ""
    modified_after: Annotated[str, msgspec.Meta(description="Only files modified on or after this date (YYYY-MM-DD)")] = ""
    modified_before: Annotated[str, msgspec.Meta(description="Only files modified before this date (YYYY-MM-DD)")] = ""
    max_depth: Annotated[int, msgspec.Meta(ge=1, le=20)] = 6
    include_hidden: bool = False
    limit: Annotated[int, msgspec.Meta(ge=1, le=500)] = 50


class FsSearch(Capability):
    name = "fs.search"
    summary = ("Find files under a folder by name glob, modification date, and (for plain-text files) contents. "
               "Use fs_read_text to read PDFs and other documents.")
    Params = SearchParams
    idempotent = True
    timeout_s = 60.0

    def resources(self, p: SearchParams, env: Env) -> list[Resource]:
        return _read_resource(env, p.path)

    def describe(self, p: SearchParams, env: Env) -> str:
        return f"Search {p.path} for {p.name}" + (f" containing “{p.text}”" if p.text else "")

    async def run(self, p: SearchParams, ctx: ActionContext) -> ActionResult:
        env = ctx.env
        root = resolve_existing(env, p.path, want_dir=True)
        after = parse_when(p.modified_after, "modified_after")
        before = parse_when(p.modified_before, "modified_before")
        needle = p.text.lower()
        found: list[tuple[Path, os.stat_result]] = []
        scanned = 0
        stopped = False
        base_depth = len(root.parts)
        for folder, dirs, files in os.walk(root):
            here = Path(folder)
            dirs[:] = sorted(d for d in dirs if (p.include_hidden or not d.startswith("."))
                             and not env.rules.skip_when_walking(here / d)
                             and len((here / d).parts) - base_depth < p.max_depth)
            for name in sorted(files):
                scanned += 1
                if scanned > MAX_SCAN or len(found) >= p.limit:
                    stopped = True
                    break
                if (not p.include_hidden and name.startswith(".")) or not fnmatch.fnmatch(name.lower(), p.name.lower()):
                    continue
                path = here / name
                if env.rules.denied(path) or env.rules.sensitive(path):
                    continue
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                if (after is not None and st.st_mtime < after) or (before is not None and st.st_mtime >= before):
                    continue
                if needle and not _contains(path, st, needle):
                    continue
                found.append((path, st))
            if stopped:
                break
        lines = "\n".join(entry_line(env, path, st, full=True) for path, st in found)
        head = f"{len(found)} match{'es' if len(found) != 1 else ''} under {env.show(root)}"
        if stopped:
            head += f" (stopped after {min(scanned, MAX_SCAN)} files or {p.limit} matches; narrow the search for more)"
        return ActionResult(ok=True, observation=f"{head}\n{lines}" if lines else head,
                            summary=f"Searched {env.show(root)}: {len(found)} found", trust="untrusted")


def _contains(path: Path, st: os.stat_result, needle: str) -> bool:
    if st.st_size > MAX_TEXT_SEARCH_BYTES or path.suffix.lower() in (".pdf", *TEXT_SUFFIXES_NOT_READABLE):
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if b"\0" in data[:8192]:
        return False
    return needle in data.decode("utf-8", "replace").lower()


# ── fs.read_text ────────────────────────────────────────────────────────────


class ReadParams(msgspec.Struct, kw_only=True):
    path: Annotated[str, msgspec.Meta(description="File to read: plain text or PDF")]
    max_chars: Annotated[int, msgspec.Meta(ge=100, le=MAX_READ_CHARS)] = 20_000
    offset: Annotated[int, msgspec.Meta(ge=0, description="Character to start from, to read further")] = 0


class FsReadText(Capability):
    name = "fs.read_text"
    summary = "Read a text file or the text of a PDF. Long files come back in parts: use offset to continue."
    Params = ReadParams
    idempotent = True

    def resources(self, p: ReadParams, env: Env) -> list[Resource]:
        return _read_resource(env, p.path)

    def describe(self, p: ReadParams, env: Env) -> str:
        return f"Read {p.path}"

    async def run(self, p: ReadParams, ctx: ActionContext) -> ActionResult:
        env = ctx.env
        path = resolve_existing(env, p.path, want_dir=False)
        if path.suffix.lower() == ".pdf":
            if env.extractor is None:
                raise CapabilityError("unavailable", "reading PDFs needs pdftotext (poppler-utils), which isn't installed")
            text = await env.extractor.pdf_text(path, p.offset + p.max_chars + 1)
        else:
            text = _read_text_file(env, path, p.offset + p.max_chars + 1)
        part = text[p.offset:p.offset + p.max_chars]
        more = len(text) > p.offset + p.max_chars
        note = f"\n[… more after character {p.offset + len(part)}; read again with offset={p.offset + len(part)}]" if more else ""
        return ActionResult(ok=True, observation=(part or "(no text)") + note, summary=f"Read {env.show(path)}",
                            data_class="file_content", trust="untrusted", sources=[str(path)])


def _read_text_file(env: Env, path: Path, limit_chars: int) -> str:
    if path.suffix.lower() in TEXT_SUFFIXES_NOT_READABLE:
        raise CapabilityError("invalid", f"{env.show(path)} isn't a text file")
    try:
        with open(path, "rb") as f:
            data = f.read(limit_chars * 4)  # UTF-8 is at most four bytes a character
    except PermissionError:
        raise CapabilityError("permission", f"no permission to read {env.show(path)}") from None
    if b"\0" in data[:8192]:
        raise CapabilityError("invalid", f"{env.show(path)} is a binary file")
    return data.decode("utf-8", "replace")[:limit_chars]
