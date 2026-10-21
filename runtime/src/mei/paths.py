"""Where Mei keeps things, following the XDG Base Directory specification."""

import os
from pathlib import Path


def _xdg(variable: str, default: str) -> Path:
    # The spec says relative values are invalid and must be ignored.
    value = os.environ.get(variable, "")
    return Path(value) if os.path.isabs(value) else Path.home() / default


def data_home() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share")


def config_home() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config")


def data_dir() -> Path:
    """Mei's store. MEI_DATA_DIR overrides it for tests and development."""
    return Path(os.environ["MEI_DATA_DIR"]) if os.environ.get("MEI_DATA_DIR") else data_home() / "mei"


def user_dirs(home: Path | None = None) -> dict[str, Path]:
    """The person's usual folders from xdg-user-dirs (`XDG_DOWNLOAD_DIR="$HOME/Downloads"`), keyed
    DOWNLOAD, DOCUMENTS, …; folders that don't exist are left out."""
    home = home or Path.home()
    found: dict[str, Path] = {}
    try:
        text = (config_home() / "user-dirs.dirs").read_text(encoding="utf-8")
    except OSError:
        text = ""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("XDG_") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip().strip('"').replace("$HOME", str(home))
        path = Path(value)
        if name.endswith("_DIR") and path.is_absolute() and path != home and path.is_dir():
            found[name[4:-4]] = path
    if not found:  # no xdg-user-dirs: the usual English names, where they exist
        for key, name in (("DOWNLOAD", "Downloads"), ("DOCUMENTS", "Documents"), ("PICTURES", "Pictures"),
                          ("MUSIC", "Music"), ("VIDEOS", "Videos"), ("DESKTOP", "Desktop")):
            if (home / name).is_dir():
                found[key] = home / name
    return found
