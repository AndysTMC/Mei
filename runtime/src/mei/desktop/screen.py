"""Whether the screen is locked, from GNOME's ScreenSaver interface (the Shell implements it): voice
closes the microphone while it is (§11.2)."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from dbus_fast import Message, MessageType
from dbus_fast.aio import MessageBus

log = logging.getLogger("mei.desktop")
SCREENSAVER = "org.gnome.ScreenSaver"


async def watch_lock(bus: MessageBus, changed: Callable[[bool], Awaitable[None]]) -> None:
    """Call `changed(locked)` now and whenever the screen locks or unlocks."""
    def on_message(msg: Message) -> None:
        if msg.message_type == MessageType.SIGNAL and msg.interface == SCREENSAVER and msg.member == "ActiveChanged":
            task = asyncio.ensure_future(changed(bool(msg.body[0])))
            task.add_done_callback(_report)

    bus.add_message_handler(on_message)
    await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                           interface="org.freedesktop.DBus", member="AddMatch", signature="s",
                           body=[f"type='signal',interface='{SCREENSAVER}',member='ActiveChanged'"]))
    reply = await bus.call(Message(destination=SCREENSAVER, path="/org/gnome/ScreenSaver", interface=SCREENSAVER,
                                   member="GetActive"))
    if reply.message_type == MessageType.METHOD_RETURN:
        await changed(bool(reply.body[0]))
    else:
        log.info("can't tell whether the screen is locked (%s); assuming it isn't", reply.error_name)


def _report(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.warning("handling the screen lock failed: %s", task.exception())
