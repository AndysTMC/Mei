"""Media players through MPRIS on the session bus (org.mpris.MediaPlayer2.*)."""

from dbus_fast import Message, MessageType
from dbus_fast.aio import MessageBus

from mei.capabilities.base import Player

PREFIX = "org.mpris.MediaPlayer2."
PATH = "/org/mpris/MediaPlayer2"
ACTIONS = {"play": "Play", "pause": "Pause", "play_pause": "PlayPause", "stop": "Stop", "next": "Next",
           "previous": "Previous"}


class Mpris:
    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus

    async def _call(self, dest: str, interface: str, member: str, signature: str = "", body=None):
        reply = await self._bus.call(Message(destination=dest, path=PATH if dest != "org.freedesktop.DBus" else
                                             "/org/freedesktop/DBus", interface=interface, member=member,
                                             signature=signature, body=body or []))
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"{dest}: {reply.error_name}: {reply.body[0] if reply.body else ''}")
        return reply.body

    async def players(self) -> list[Player]:
        [names] = await self._call("org.freedesktop.DBus", "org.freedesktop.DBus", "ListNames")
        found = []
        for name in sorted(n for n in names if n.startswith(PREFIX)):
            try:
                [root] = await self._call(name, "org.freedesktop.DBus.Properties", "GetAll", "s",
                                          ["org.mpris.MediaPlayer2"])
                [player] = await self._call(name, "org.freedesktop.DBus.Properties", "GetAll", "s",
                                            ["org.mpris.MediaPlayer2.Player"])
            except RuntimeError:
                continue  # it left, or isn't a full MPRIS player
            meta = player.get("Metadata").value if "Metadata" in player else {}
            artists = meta.get("xesam:artist").value if "xesam:artist" in meta else []
            found.append(Player(name=name.removeprefix(PREFIX), identity=str(root["Identity"].value)
                                if "Identity" in root else name.removeprefix(PREFIX),
                                status=str(player["PlaybackStatus"].value) if "PlaybackStatus" in player else "",
                                title=str(meta["xesam:title"].value) if "xesam:title" in meta else "",
                                artist=", ".join(map(str, artists))))
        return found

    async def control(self, name: str, action: str) -> None:
        await self._call(PREFIX + name, "org.mpris.MediaPlayer2.Player", ACTIONS[action])
