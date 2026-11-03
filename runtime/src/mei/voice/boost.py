"""The words Mei listens for (decision 0029): the names a recognizer gets wrong because it has never
heard them. The clean-up chain's Boost step puts them back where something close was heard.

- **Apps** installed here, by the names their menus show.
- **Learned:** names from what Mei remembers about the person and from what they wrote to Mei lately
  (capitalised words that aren't ordinary words). They stay on this computer like the rest.
- **Yours:** the list in Settings.
"""

import os
import re
from collections import Counter
from pathlib import Path

from .cleanup import _dictionary

SYSTEM_FLATPAK = Path("/var/lib/flatpak/exports/share")
RECENT_MESSAGES = 200
MAX_LEARNED = 100
_NAME = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-zA-Z]{3,}\b")


def app_names() -> list[str]:
    """The Name= of each installed app's .desktop file that a menu shows."""
    dirs = [Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")]
    dirs += [Path(d) for d in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if d]
    dirs += [Path.home() / ".local/share/flatpak/exports/share", SYSTEM_FLATPAK]
    names: dict[str, None] = {}
    for d in dict.fromkeys(dirs):
        folder = d / "applications"
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.desktop")):
            name = _desktop_name(path)
            if name:
                names.setdefault(name)
    return list(names)


def _desktop_name(path: Path) -> str | None:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return None
    entry = text.split("[Desktop Entry]", 1)[-1].split("\n[", 1)[0]
    fields = dict(line.split("=", 1) for line in entry.splitlines() if "=" in line and not line.startswith("#"))
    if fields.get("NoDisplay", "").lower() == "true" or fields.get("Hidden", "").lower() == "true":
        return None
    return fields.get("Name", "").strip() or None


def learned(store) -> list[str]:
    """Names in active memories and the person's recent messages, most used first."""
    ordinary = _dictionary()
    if ordinary is None:
        return []
    texts = [r["text"] for r in store.read("SELECT text FROM memories WHERE status = 'active'")]
    texts += [r["content"] for r in store.read(
        "SELECT content FROM messages WHERE role = 'user' ORDER BY created_at DESC LIMIT ?", (RECENT_MESSAGES,))]
    counts = Counter(m.group(0) for t in texts for m in _NAME.finditer(t) if m.group(0).lower() not in ordinary)
    return [w for w, _ in counts.most_common(MAX_LEARNED)]


def words(store, yours: list[str]) -> dict[str, list[str]]:
    """Each source's words, for Settings and for the Boost step."""
    found = {"apps": app_names(), "learned": [], "yours": [w.strip() for w in yours if w.strip()]}
    if store is not None:
        found["learned"] = learned(store)
    return found
