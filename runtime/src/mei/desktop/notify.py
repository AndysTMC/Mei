"""Desktop notifications over the session bus (org.freedesktop.Notifications)."""

from dbus_fast import Message, MessageType
from dbus_fast.aio import MessageBus
from dbus_fast.signature import Variant

APP_NAME = "Mei"


class BusNotifier:
    def __init__(self, bus: MessageBus) -> None:
        self._bus = bus

    async def notify(self, title: str, body: str) -> int:
        reply = await self._bus.call(Message(
            destination="org.freedesktop.Notifications", path="/org/freedesktop/Notifications",
            interface="org.freedesktop.Notifications", member="Notify", signature="susssasa{sv}i",
            body=[APP_NAME, 0, "", title, body, [], {"urgency": Variant("y", 1)}, -1]))
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"notifications: {reply.error_name}: {reply.body[0] if reply.body else ''}")
        return int(reply.body[0])
