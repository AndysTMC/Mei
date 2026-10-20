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
