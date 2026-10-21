"""Who is calling (§13.7): approvals and answers are taken only from the GNOME Shell process.

The caller's unique name maps to a pid through the bus daemon, and the pid to its executable. It
must be `gnome-shell`, and a file this user can't modify. Defense against casual misuse by other
local programs, not against malware running as the same user.
"""

import logging
import os

from dbus_fast import Message, MessageType
from dbus_fast.aio import MessageBus

log = logging.getLogger("mei.ipc")
SHELL = "gnome-shell"


async def caller_pid(bus: MessageBus, sender: str) -> int | None:
    reply = await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                   interface="org.freedesktop.DBus", member="GetConnectionUnixProcessID",
                                   signature="s", body=[sender]))
    if reply.message_type == MessageType.ERROR or not reply.body:
        return None
    return int(reply.body[0])


def is_shell_executable(pid: int) -> bool:
    try:
        exe = os.path.realpath(f"/proc/{pid}/exe", strict=True)
    except OSError:
        return False
    return os.path.basename(exe) == SHELL and not os.access(exe, os.W_OK)


def shell_check(bus: MessageBus):
    async def is_shell(sender: str) -> bool:
        pid = await caller_pid(bus, sender)
        ok = pid is not None and is_shell_executable(pid)
        if not ok:
            log.warning("refused a Shell-only call from %s (pid %s)", sender, pid)
        return ok

    return is_shell
