"""Where an action's resources came from (§13.4).

- user-anchored: the person named it, or a folder holding it, in their own messages;
- untrusted: it (or a folder holding it) first showed up in content others could have written;
- model-derived: neither.

A conservative textual check, not data-flow tracking: it removes most needless prompts (a folder
the person named) and keeps prompts for paths a document or web page suggested.
"""

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


def anchors(user_texts: list[str], env: Env) -> list[Path]:
    """Folders and files the person named. Home and `/` themselves are too broad to count."""
    found: list[Path] = []
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


def classify(path: Path, anchored: list[Path], untrusted_texts: list[str], env: Env) -> Provenance:
    if any(inside(path, a) for a in anchored):
        return "user"
    if _mentioned(path, untrusted_texts, env):
        return "untrusted"
    return "model"


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
