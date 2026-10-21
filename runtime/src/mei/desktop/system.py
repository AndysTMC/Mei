"""What `system.status` reports: battery (UPower on the system bus), disk, memory, load, uptime."""

import shutil
from pathlib import Path

from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus

_BATTERY_STATES = {1: "charging", 2: "discharging", 3: "empty", 4: "fully charged", 5: "pending charge",
                   6: "pending discharge"}


class SystemStatus:
    def __init__(self, home: Path) -> None:
        self._home = home

    async def read(self) -> dict:
        status: dict = {"disk": _disk(self._home), "memory": _memory(), "load": _load(), "uptime_h": _uptime_h()}
        battery = await _battery()
        if battery is not None:
            status["battery"] = battery
        return status


async def _battery() -> dict | None:
    try:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    except (OSError, EOFError):
        return None
    try:
        reply = await bus.call(Message(destination="org.freedesktop.UPower",
                                       path="/org/freedesktop/UPower/devices/DisplayDevice",
                                       interface="org.freedesktop.DBus.Properties", member="GetAll", signature="s",
                                       body=["org.freedesktop.UPower.Device"]))
    finally:
        bus.disconnect()
    if reply.message_type == MessageType.ERROR or not reply.body:
        return None
    props = reply.body[0]
    if not props.get("IsPresent") or not props["IsPresent"].value:
        return None  # a desktop without a battery
    return {"percent": round(props["Percentage"].value), "state": _BATTERY_STATES.get(props["State"].value, "unknown")}


def _disk(home: Path) -> dict:
    usage = shutil.disk_usage(home)
    return {"free_gb": round(usage.free / 1e9, 1), "total_gb": round(usage.total / 1e9, 1)}


def _memory() -> dict:
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        info[key] = int(rest.split()[0]) if rest.split() else 0
    return {"available_gb": round(info.get("MemAvailable", 0) / 1e6, 1), "total_gb": round(info.get("MemTotal", 0) / 1e6, 1)}


def _load() -> float:
    return float(Path("/proc/loadavg").read_text().split()[0])


def _uptime_h() -> float:
    return round(float(Path("/proc/uptime").read_text().split()[0]) / 3600, 1)
