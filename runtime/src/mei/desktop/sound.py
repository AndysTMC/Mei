"""The default output's volume through PipeWire's `wpctl`."""

import re

from .run import ToolFailed, checked

WPCTL = "/usr/bin/wpctl"
SINK = "@DEFAULT_AUDIO_SINK@"
_VOLUME = re.compile(r"Volume:\s*([0-9.]+)(\s*\[MUTED\])?")


class Wpctl:
    def __init__(self, tool: str = WPCTL) -> None:
        self._tool = tool

    async def get(self) -> tuple[int, bool]:
        """(percent, muted)."""
        out = await checked([self._tool, "get-volume", SINK])
        match = _VOLUME.search(out)
        if not match:
            raise ToolFailed(f"wpctl: unexpected output {out.strip()!r}")
        return round(float(match.group(1)) * 100), bool(match.group(2))

    async def set(self, percent: int, muted: bool) -> None:
        await checked([self._tool, "set-volume", "-l", "1.0", SINK, f"{max(0, min(100, percent)) / 100:.2f}"])
        await checked([self._tool, "set-mute", SINK, "1" if muted else "0"])
