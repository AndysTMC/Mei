"""Where an action's resources came from (§13.4).

- user-anchored: the person named it, or a folder holding it, in this task's own messages (or
  dropped it on Mei with one of them);
- untrusted: it (or a folder holding it) showed up in content others could have written;
- model-derived: neither.

Whether the person named the item itself (not only its folder) is kept separately: after Mei has
read a document in the task, only that counts for changing things without a card (policy/engine.py).

A conservative textual check, not data-flow tracking: it removes most needless prompts (a folder
the person named) and keeps prompts for paths a document or web page suggested.
"""

import os
import re
from pathlib import Path
from typing import Literal

from mei.capabilities.base import Env

from .paths import inside

Provenance = Literal["user", "untrusted", "model"]

# Path-like words: `~/x`, `/x/y`, `Documents/Invoices/2026`; quoted names may contain spaces.
_PATH = re.compile(r"(?<![\w/~.])(?:~(?=/|\b)|/|[\w.@+-]+/)[\w.@+\-/~]*")
_QUOTED = re.compile(r"(?<!\w)[\"'“‘`]([^\"'”’`\n]{1,300})[\"'”’`](?!\w)")  # not the ' in "week's"
_TRAILING = ".,;:!?)]}>"
# English names for the xdg-user-dirs folders, so "my Downloads" anchors the real (maybe localized) folder.
_XDG_WORDS = {"DOWNLOAD": ("downloads", "download"), "DOCUMENTS": ("documents",), "PICTURES": ("pictures", "photos"),
              "MUSIC": ("music",), "VIDEOS": ("videos",), "DESKTOP": ("desktop",), "TEMPLATES": ("templates",),
              "PUBLICSHARE": ("public",)}


def anchors(user_texts: list[str], env: Env, pointed: tuple[Path, ...] = ()) -> list[Path]:
    """Folders and files the person named, in words or by dropping them on Mei (`pointed`). Home and
    `/` themselves are too broad to count."""
    found: list[Path] = list(pointed)
    for text in user_texts:
        quoted = [q for q in _QUOTED.findall(text) if "/" in q or q.startswith("~")]
        rest = _QUOTED.sub(" ", text)  # a quoted path with spaces is one path, not several words
        for candidate in quoted + _PATH.findall(rest):
            cleaned = candidate.rstrip(_TRAILING)
            if not cleaned or cleaned in ("/", "~", "~/"):
                continue
            try:
                found.append(env.path(cleaned))
            except ValueError:
                continue
        # Folder names said on their own ("in Downloads"), not as part of a longer path ("Documents/Invoices"
        # names Invoices, not all of Documents).
        words = set(re.findall(r"[\w-]+", _PATH.sub(" ", rest).lower()))
        for key, folder in env.user_dirs.items():
            names = {*_XDG_WORDS.get(key, ()), folder.name.lower()}
            if words & names:
                found.append(folder)
    return [a for a in dict.fromkeys(found) if a not in (env.home, Path("/"))]


def views(path: Path) -> list[Path]:
    """A path as written and where it really leads (symlinks in its existing folders resolved)."""
    real = Path(os.path.realpath(path))
    return [path] if real == path else [path, real]


def named(path: Path, anchored: list[Path], user_texts: list[str]) -> bool:
    """Did the person name this exact thing: its path, or a file by its own name ("notes.txt")?
    Being inside a folder they named is weaker, and doesn't count here."""
    if any(v in anchored for v in views(path)):
        return True
    name = path.name.lower()
    return len(name) >= 3 and any(name in set(_TOKEN.findall(t.lower())) for t in user_texts)


def classify(path: Path, anchored: list[Path], untrusted_content: list[str], untrusted_other: list[str],
             env: Env, *, is_named: bool) -> Provenance:
    """Where a path came from. Judged by every view of it, so a symlink inside a named folder that
    leads out of it isn't "in" that folder. Content Mei read that names this very item outweighs the
    folder: a document saying "trash ~/Downloads/contract.pdf" makes that path untrusted."""
    if is_named:
        return "user"
    seen = views(path)
    if all(any(inside(v, a) for a in anchored) for v in seen):
        return "untrusted" if any(_names_item(v, untrusted_content, env) for v in seen) else "user"
    if any(_mentioned(v, untrusted_content + untrusted_other, env) for v in seen):
        return "untrusted"
    return "model"


def resolved_anchors(found: list[Path]) -> list[Path]:
    """Anchors as written and as they resolve (a Downloads that is a link to another drive)."""
    return list(dict.fromkeys(v for a in found for v in views(a)))


def _names_item(path: Path, texts: list[str], env: Env) -> bool:
    """Do these texts name this item itself (its path, or its file name), not just a folder above it?"""
    forms = {str(path), env.show(path)}
    if inside(path, env.home) and path != env.home:
        forms.add(str(path.relative_to(env.home)))
    tokens = [set(_TOKEN.findall(t.lower())) for t in texts]
    name = path.name.lower()
    return any(form in t for form in forms if len(form) >= 3 for t in texts) or \
        (len(name) >= 4 and any(name in tok for tok in tokens))


def _mentioned(path: Path, texts: list[str], env: Env) -> bool:
    """Did this path, or a folder holding it (below home), appear in untrusted content?"""
    if not texts:
        return False
    for p in [path, *path.parents]:
        if p in (env.home, Path("/")) or (not inside(p, env.home) and p.parent == Path("/")):
            break  # home and top-level folders are too broad to say anything
        forms = {str(p), env.show(p)}
        if inside(p, env.home):
            forms.add(str(p.relative_to(env.home)))  # "Documents/Invoices", as a document would write it
        if any(form in text for form in forms if len(form) >= 3 for text in texts):
            return True
    return False


_TOKEN = re.compile(r"\w+(?:[.-]\w+)*")
