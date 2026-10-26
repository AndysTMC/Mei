"""A PNG's size from its header, without decoding it (the pictures computer use keeps, PDF pages)."""

from pathlib import Path


def png_size(path: Path) -> tuple[int, int] | None:
    """Width and height; None if the file is gone or isn't a PNG."""
    try:
        with path.open("rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
