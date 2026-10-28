"""Who is calling (§13.7): approvals and answers are taken only from the GNOME Shell process.

The caller must be the connection that owns `org.gnome.Shell` on the session bus right now (decision
0031): a program can't take that name while the Shell holds it, whatever its file is called. As a
second check, its pid (from the bus daemon) must run `gnome-shell` from a file this user can't
modify. Defense against casual misuse by other local programs, not against malware running as the
same user (it could replace the Shell's extension itself).
"""

from collections.abc import Awaitable, Callable

import logging
import os

from dbus_fast import Message, MessageType
from dbus_fast.aio import MessageBus

log = logging.getLogger("mei.ipc")
SHELL = "gnome-shell"
SHELL_NAME = "org.gnome.Shell"


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


async def name_owner(bus: MessageBus, name: str) -> str | None:
    reply = await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                   interface="org.freedesktop.DBus", member="GetNameOwner", signature="s", body=[name]))
    if reply.message_type == MessageType.ERROR or not reply.body:
        return None
    return str(reply.body[0])


def shell_check(bus: MessageBus,
                executable: Callable[[int], bool] = is_shell_executable) -> Callable[[str], Awaitable[bool]]:
    async def is_shell(sender: str) -> bool:
        owner = await name_owner(bus, SHELL_NAME)
        pid = await caller_pid(bus, sender) if owner == sender else None
        ok = pid is not None and executable(pid)
        if not ok:
            log.warning("refused a Shell-only call from %s (pid %s)", sender, pid)
        return ok

    return is_shell
