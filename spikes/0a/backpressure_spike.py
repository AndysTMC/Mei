"""Stage 0a: does the runtime survive a full socket buffer? Usage: backpressure_spike.py [patched]

Starts a sender and a receiver on the current (private) session bus. The sender fires bursts of
unicast signals as fast as it can; the receiver reads normally. Reports whether the sender's bus
connection survived each burst.
"""

import asyncio
import json
import sys
import time

from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus

if len(sys.argv) > 1 and sys.argv[1] == "patched":
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    import dbus_fast_patch

    dbus_fast_patch.apply()

BURSTS, PER_BURST = 10, 20000
PAYLOAD = "x" * 400


async def main() -> None:
    sender = await MessageBus(bus_type=BusType.SESSION).connect()
    receiver = await MessageBus(bus_type=BusType.SESSION).connect()
    got = 0

    def on_msg(msg):
        nonlocal got
        if msg.message_type == MessageType.SIGNAL and msg.member == "Event":
            got += 1

    receiver.add_message_handler(on_msg)
    survived = 0
    t0 = time.monotonic()
    for b in range(BURSTS):
        for i in range(PER_BURST):
            sender.send(Message(message_type=MessageType.SIGNAL, destination=receiver.unique_name,
                                path="/x", interface="com.andystmc.Spike", member="Event",
                                signature="s", body=[PAYLOAD]))
        await asyncio.sleep(0)
        await sender.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                  interface="org.freedesktop.DBus", member="GetId"))  # flushes the queue
        if not sender.connected:
            break
        survived += 1
    expected = survived * PER_BURST
    deadline = time.monotonic() + 30
    while got < expected and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    print(json.dumps({"patched": "dbus_fast_patch" in sys.modules, "bursts_survived": survived,
                      "of": BURSTS, "signals_sent": expected, "signals_received": got,
                      "seconds": round(time.monotonic() - t0, 2)}))


try:
    asyncio.run(main())
except Exception as e:
    print(json.dumps({"patched": "dbus_fast_patch" in sys.modules, "crashed": f"{type(e).__name__}: {e}"}))
