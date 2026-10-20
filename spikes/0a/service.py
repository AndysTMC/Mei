"""Stage 0a spike: minimal Mei runtime IPC surface on dbus-fast.

Implements the §12 shape: JSON-in/JSON-out methods, unicast `Event` signals with a global
sequence, Attach(after_seq) replay, and ReadArtifact returning (sh) with a read-only fd.
Throwaway code; not the runtime.
"""

import asyncio
import faulthandler
import signal
import traceback
import hashlib
import json
import os
import sys
import tempfile
import time
import uuid

from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dbus_fast_patch  # noqa: E402

dbus_fast_patch.apply()

NAME = os.environ.get("MEI_SPIKE_NAME", "com.andystmc.Mei1")
PATH = "/com/andystmc/Mei1"
IFACE = "com.andystmc.Mei1.Runtime"
TICK_S = 0.1
ARTIFACT = b"mei spike artifact " * 4096  # ~76 KiB

epoch = str(uuid.uuid4())
seq = 0
events: list[tuple[int, str]] = []
clients: set[str] = set()
open_fds: list[int] = []
artifact_dir = tempfile.mkdtemp(prefix="mei-spike-artifacts-")
artifact_path = os.path.join(artifact_dir, hashlib.sha256(ARTIFACT).hexdigest())
with open(artifact_path, "wb") as f:
    f.write(ARTIFACT)
os.chmod(artifact_path, 0o400)


LOG_PATH = os.path.join(os.environ.get("XDG_STATE_HOME", tempfile.gettempdir()), "mei-spike-service.log")
_log_file = open(LOG_PATH, "a", buffering=1)
faulthandler.enable(_log_file)


def log(msg: str) -> None:
    line = f"[service {time.monotonic():.3f} pid={os.getpid()}] {msg}"
    print(line, file=sys.stderr, flush=True)
    print(line, file=_log_file)


def next_event(kind: str, extra: dict | None = None) -> tuple[int, str]:
    global seq
    seq += 1
    body = {"v": 1, "type": kind, "seq": seq, "epoch": epoch, "t_ns": time.monotonic_ns()}
    if extra:
        body.update(extra)
    item = (seq, json.dumps(body))
    events.append(item)
    if len(events) > 20000:
        del events[:10000]
    return item


def emit(bus: MessageBus, item: tuple[int, str], only: str | None = None) -> None:
    for dest in [only] if only else list(clients):
        bus.send(Message(message_type=MessageType.SIGNAL, destination=dest, path=PATH,
                         interface=IFACE, member="Event", signature="s", body=[item[1]]))


def reply_json(msg: Message, data: dict) -> Message:
    return Message.new_method_return(msg, "s", [json.dumps(data)])


def make_handler(bus: MessageBus):
    def handler(msg: Message):
        if (msg.message_type == MessageType.SIGNAL and msg.member == "NameOwnerChanged"
                and msg.sender == "org.freedesktop.DBus"):
            name, _old, new = msg.body
            if not new and name in clients:
                clients.discard(name)
                log(f"client gone {name}")
            return None
        if msg.message_type != MessageType.METHOD_CALL or msg.interface != IFACE or msg.path != PATH:
            return None
        args = json.loads(msg.body[0]) if msg.body else {}
        if msg.member == "Hello":
            clients.add(msg.sender)
            log(f"hello from {msg.sender} {args}")
            return reply_json(msg, {"epoch": epoch, "seq": seq, "protocol": [1, 0], "pid": os.getpid()})
        if msg.member == "Detach":
            clients.discard(msg.sender)
            log(f"detach {msg.sender}")
            return reply_json(msg, {})
        if msg.member == "Attach":
            after = int(args.get("after_seq", 0))
            oldest = events[0][0] if events else seq + 1
            replay = [e for s, e in events if s > after] if after + 1 >= oldest else None
            return reply_json(msg, {"epoch": epoch, "seq": seq,
                                    "events": replay if replay is not None else [],
                                    "snapshot_reset": replay is None})
        if msg.member == "Ping":
            return reply_json(msg, {"t_ns": time.monotonic_ns()})
        if msg.member == "ReadArtifact":
            fd = os.open(artifact_path, os.O_RDONLY | os.O_CLOEXEC)
            open_fds.append(fd)
            meta = {"size": len(ARTIFACT), "sha256": hashlib.sha256(ARTIFACT).hexdigest()}
            return Message.new_method_return(msg, "sh", [json.dumps(meta), 0], unix_fds=[fd])
        if msg.member == "Burst":
            n = int(args.get("n", 1000))
            t0 = time.monotonic()
            for _ in range(n):
                emit(bus, next_event("burst"), only=msg.sender)
            log(f"burst n={n} queued in {1000 * (time.monotonic() - t0):.1f} ms")
            return reply_json(msg, {"n": n, "last_seq": seq})
        return Message.new_error(msg, "org.freedesktop.DBus.Error.UnknownMethod", msg.member)

    return handler


async def ticker(bus: MessageBus) -> None:
    n = 0
    while True:
        await asyncio.sleep(TICK_S)
        emit(bus, next_event("tick"))
        n += 1
        if n % 10 == 0:  # control: one broadcast per second, so the unicast check has a baseline
            bus.send(Message(message_type=MessageType.SIGNAL, path=PATH, interface=IFACE,
                             member="Beacon", signature="s", body=[str(n)]))
        while len(open_fds) > 8:
            os.close(open_fds.pop(0))


async def main() -> None:
    t0 = time.monotonic()
    bus = await MessageBus(bus_type=BusType.SESSION, negotiate_unix_fd=True).connect()
    bus.add_message_handler(make_handler(bus))
    await bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                           interface="org.freedesktop.DBus", member="AddMatch", signature="s",
                           body=["type='signal',sender='org.freedesktop.DBus',member='NameOwnerChanged'"]))
    await bus.request_name(NAME)
    log(f"owned {NAME} as {bus.unique_name} epoch={epoch} startup_ms={1000 * (time.monotonic() - t0):.1f}")
    await asyncio.gather(ticker(bus), bus.wait_for_disconnect())


if __name__ == "__main__":
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, lambda n, _f: (log(f"exiting on signal {n}"), sys.exit(0)))
    try:
        asyncio.run(main())
        log("main returned (bus disconnected)")
    except BaseException as e:
        log(f"exiting on {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise
