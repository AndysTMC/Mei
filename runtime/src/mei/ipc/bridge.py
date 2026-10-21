"""The runtime's side of the ShellBridge (§12.6): narrow calls into the Shell extension.

The extension exports `com.andystmc.Mei1.ShellBridge` on its own connection and names the object
in Hello. Methods take and return one JSON string, like the runtime's own interface.
"""

import asyncio
import json

from dbus_fast import Message, MessageType
from dbus_fast.aio import MessageBus

from mei.capabilities.base import Window

INTERFACE = "com.andystmc.Mei1.ShellBridge"
CALL_TIMEOUT_S = 5.0


class BridgeError(RuntimeError):
    pass


class ShellBridgeClient:
    def __init__(self, bus: MessageBus, name: str, path: str) -> None:
        self.name = name
        self._bus = bus
        self._path = path

    async def _call(self, member: str, args: dict) -> dict:
        try:
            async with asyncio.timeout(CALL_TIMEOUT_S):
                reply = await self._bus.call(Message(destination=self.name, path=self._path, interface=INTERFACE,
                                                     member=member, signature="s", body=[json.dumps(args)]))
        except TimeoutError:
            raise BridgeError(f"the Shell didn't answer {member} within {CALL_TIMEOUT_S:.0f} s") from None
        if reply.message_type == MessageType.ERROR:
            raise BridgeError(f"the Shell refused {member}: {reply.body[0] if reply.body else reply.error_name}")
        try:
            value = json.loads(reply.body[0])
        except (IndexError, TypeError, ValueError):
            raise BridgeError(f"the Shell's {member} reply wasn't JSON") from None
        if not isinstance(value, dict):
            raise BridgeError(f"the Shell's {member} reply wasn't an object")
        return value

    async def list_windows(self) -> list[Window]:
        reply = await self._call("ListWindows", {})
        return [Window(app_id=str(w.get("app_id", "")), title=str(w.get("title", "")), focused=bool(w.get("focused")))
                for w in reply.get("windows", []) if isinstance(w, dict)]

    async def launch_app(self, app_id: str, uris: list[str]) -> None:
        await self._call("LaunchApp", {"app_id": app_id, "uris": uris})
