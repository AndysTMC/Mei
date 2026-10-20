"""Stage 0a spike: the same client calls with dbus-fast (uv venv) and PyGObject (system python3-gi).

Run with either interpreter on a bus where service.py is activatable:
  <venv>/bin/python client_bench.py fast
  /usr/bin/python3 client_bench.py gi
"""

import asyncio
import json
import os
import resource
import sys
import time

NAME = os.environ.get("MEI_SPIKE_NAME", "com.andystmc.Mei1")
PATH, IFACE = "/com/andystmc/Mei1", "com.andystmc.Mei1.Runtime"
N = 2000


def report(lib: str, t_import: float, rtts: list[float], events: int, fd_ok: bool) -> None:
    rtts.sort()
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(json.dumps({"lib": lib, "python": sys.version.split()[0], "import_ms": round(t_import, 1),
                      "ping_p50_ms": round(rtts[len(rtts) // 2], 3), "ping_p99_ms": round(rtts[int(0.99 * len(rtts))], 3),
                      "unicast_events_in_1s": events, "fd_ok": fd_ok, "max_rss_mb": round(rss, 1)}))


async def run_fast() -> None:
    t0 = time.perf_counter()
    from dbus_fast import BusType, Message, MessageType
    from dbus_fast.aio import MessageBus
    t_import = (time.perf_counter() - t0) * 1000
    bus = await MessageBus(bus_type=BusType.SESSION, negotiate_unix_fd=True).connect()
    events = 0

    def on_msg(msg):
        nonlocal events
        if msg.message_type == MessageType.SIGNAL and msg.member == "Event":
            events += 1

    bus.add_message_handler(on_msg)

    async def call(member, sig="s", body=("{}",)):
        return await bus.call(Message(destination=NAME, path=PATH, interface=IFACE, member=member,
                                      signature=sig, body=list(body)))

    await call("Hello")
    rtts = []
    for _ in range(N):
        t = time.perf_counter()
        await call("Ping")
        rtts.append((time.perf_counter() - t) * 1000)
    events = 0
    await asyncio.sleep(1.0)
    reply = await call("ReadArtifact")
    meta = json.loads(reply.body[0])
    fd = reply.unix_fds[reply.body[1]]
    data = os.read(fd, meta["size"] + 1)
    os.close(fd)
    report("dbus-fast", t_import, rtts, events, len(data) == meta["size"])


async def run_gi() -> None:
    t0 = time.perf_counter()
    import gi
    gi.require_version("Gio", "2.0")
    gi.require_version("GioUnix", "2.0")
    from gi.events import GLibEventLoopPolicy
    from gi.repository import Gio, GioUnix, GLib  # noqa: F401
    t_import = (time.perf_counter() - t0) * 1000
    conn = await Gio.bus_get(Gio.BusType.SESSION)
    events = 0

    def on_signal(*_):
        nonlocal events
        events += 1

    conn.signal_subscribe(NAME, IFACE, "Event", PATH, None, Gio.DBusSignalFlags.NONE, on_signal)

    async def call(member):
        return await conn.call(NAME, PATH, IFACE, member, GLib.Variant("(s)", ("{}",)), None,
                               Gio.DBusCallFlags.NONE, 5000)

    await call("Hello")
    rtts = []
    for _ in range(N):
        t = time.perf_counter()
        await call("Ping")
        rtts.append((time.perf_counter() - t) * 1000)
    events = 0
    await asyncio.sleep(1.0)
    ret, fdlist = await conn.call_with_unix_fd_list(NAME, PATH, IFACE, "ReadArtifact",
                                                    GLib.Variant("(s)", ("{}",)), GLib.VariantType("(sh)"),
                                                    Gio.DBusCallFlags.NONE, 5000, None)
    meta_json, idx = ret.unpack()
    meta = json.loads(meta_json)
    fd = fdlist.get(idx)
    data = os.read(fd, meta["size"] + 1)
    os.close(fd)
    report("pygobject", t_import, rtts, events, len(data) == meta["size"])


if __name__ == "__main__":
    if sys.argv[1] == "gi":
        # Documented PyGObject >= 3.50 pattern; asyncio.run() with the policy fails on 3.14.
        from gi.events import GLibEventLoopPolicy
        policy = GLibEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
        policy.get_event_loop().run_until_complete(run_gi())
    else:
        asyncio.run(run_fast())
