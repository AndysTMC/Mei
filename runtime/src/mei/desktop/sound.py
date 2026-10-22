"""Volume through PipeWire's `wpctl`: the default output's, or the microphone's (its capture level)."""

import re

from .run import ToolFailed, checked

WPCTL = "/usr/bin/wpctl"
SINK = "@DEFAULT_AUDIO_SINK@"
SOURCE = "@DEFAULT_AUDIO_SOURCE@"
_VOLUME = re.compile(r"Volume:\s*([0-9.]+)(\s*\[MUTED\])?")


class Wpctl:
    def __init__(self, tool: str = WPCTL, node: str = SINK) -> None:
        self._tool = tool
        self._node = node

    async def get(self) -> tuple[int, bool]:
        """(percent, muted)."""
        out = await checked([self._tool, "get-volume", self._node])
        match = _VOLUME.search(out)
        if not match:
            raise ToolFailed(f"wpctl: unexpected output {out.strip()!r}")
        return round(float(match.group(1)) * 100), bool(match.group(2))

    async def set(self, percent: int, muted: bool) -> None:
        await checked([self._tool, "set-volume", "-l", "1.0", self._node, f"{max(0, min(100, percent)) / 100:.2f}"])
        await checked([self._tool, "set-mute", self._node, "1" if muted else "0"])
