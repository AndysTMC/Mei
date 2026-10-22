"""Volume through PipeWire's `wpctl`: the default output's, or the microphone's (its capture level).
And which microphones and speakers there are, from `pw-dump`, which reads the graph and opens no audio."""

import json
import re

from .run import ToolFailed, checked

WPCTL = "/usr/bin/wpctl"
PW_DUMP = "/usr/bin/pw-dump"
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


async def audio_devices(tool: str = PW_DUMP) -> dict[str, list[dict]]:
    """{"mics": [...], "outputs": [...]}, each {"id", "name", "label"}: `name` is the node name the
    voice settings keep (ids change between sessions), `label` what the person sees."""
    try:
        graph = json.loads(await checked([tool]))
    except ValueError:
        raise ToolFailed("pw-dump: unexpected output") from None
    found: dict[str, list[dict]] = {"mics": [], "outputs": []}
    for obj in graph if isinstance(graph, list) else []:
        props = (obj.get("info") or {}).get("props") or {}
        kind = str(props.get("media.class", ""))
        key = "mics" if kind.startswith("Audio/Source") else "outputs" if kind.startswith("Audio/Sink") else ""
        name = props.get("node.name")
        if obj.get("type") != "PipeWire:Interface:Node" or not key or not isinstance(name, str):
            continue
        found[key].append({"id": obj.get("id"), "name": name,
                           "label": str(props.get("node.description") or props.get("node.nick") or name)})
    return found
