"""Runs inside a private session (see test_key_privacy.py). Puts an API key in the keyring, watches
every message on the bus, and drives each Mei method that needs the key: model listing, the setup
check, a provider test, a chat turn, and a turn whose upstream error echoes the key back. Prints one
JSON result: whether the key appeared in any message of Mei's own interface."""

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus

from mei.secrets import store_provider_key

NAME, PATH, IFACE = "com.andystmc.Mei1", "/com/andystmc/Mei1", "com.andystmc.Mei1.Runtime"
KEY = "mei-test-key-7Q2x9Lp4Zr8Vn3Kd"  # no known key prefix: only exact-value scrubbing can catch it
SEEN_AUTH: list[str] = []


class MockOpenAI(BaseHTTPRequestHandler):
    def _auth(self) -> None:
        SEEN_AUTH.append(self.headers.get("authorization", ""))

    def do_GET(self):
        self._auth()
        self._json(200, {"data": [{"id": "mock-1"}, {"id": "mock-2"}]})

    def do_POST(self):
        self._auth()
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        if "fail inside the stream" in body["messages"][-1]["content"]:
            # An error frame inside a successful (200) stream, also repeating the key.
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: " + json.dumps({"error": {"message": f"Invalid key {KEY}"}}).encode() + b"\n\n")
            return
        if "fail" in body["messages"][-1]["content"]:
            # Like OpenAI's 401, which repeats the key it was given.
            self._json(401, {"error": {"message": f"Incorrect API key provided: {KEY}"}})
            return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        for piece in ("OK", ", ready."):
            self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")

    def _json(self, status: int, data: dict) -> None:
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        pass


class Monitor:
    """Every message on the bus, through org.freedesktop.DBus.Monitoring."""

    def __init__(self) -> None:
        self.messages: list[Message] = []

    async def start(self) -> None:
        self.bus = await MessageBus(bus_type=BusType.SESSION).connect()
        await self.bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                    interface="org.freedesktop.DBus.Monitoring", member="BecomeMonitor",
                                    signature="asu", body=[[], 0]))
        self.bus.add_message_handler(self._on)

    def _on(self, msg: Message):
        self.messages.append(msg)
        # Claim observed method calls so dbus-fast doesn't answer them: a monitor must never send.
        return msg.message_type == MessageType.METHOD_CALL or None

    def mei_messages(self) -> list[Message]:
        calls = {(m.sender, m.serial) for m in self.messages
                 if m.message_type == MessageType.METHOD_CALL and m.interface == IFACE}
        return [m for m in self.messages
                if (m.message_type in (MessageType.METHOD_CALL, MessageType.SIGNAL) and m.interface == IFACE)
                or (m.message_type in (MessageType.METHOD_RETURN, MessageType.ERROR)
                    and (m.destination, m.reply_serial) in calls)]


async def call(bus, member, args=None, timeout=30):
    reply = await asyncio.wait_for(bus.call(Message(destination=NAME, path=PATH, interface=IFACE, member=member,
                                                    signature="s", body=[json.dumps(args or {})])), timeout)
    if reply.message_type == MessageType.ERROR:
        raise RuntimeError(f"{reply.error_name}: {reply.body}")
    return json.loads(reply.body[0])


async def turn(bus, finished: dict, text: str, conversation_id=None) -> dict:
    args = {"command_id": f"cmd-{text}", "text": text}
    if conversation_id:
        args["conversation_id"] = conversation_id
    r = await call(bus, "SubmitInput", args)
    async with asyncio.timeout(30):
        while r["task_id"] not in finished:
            await asyncio.sleep(0.05)
    return {**r, "finished": finished[r["task_id"]]}


async def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockOpenAI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1/chat/completions"

    port = server.server_address[1]
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    monitor = Monitor()
    await monitor.start()
    await store_provider_key(bus, "openai", KEY)  # what Settings does, through the keyring only

    finished: dict[str, dict] = {}

    def on_event(msg: Message):
        if msg.message_type == MessageType.SIGNAL and msg.member == "Event" and msg.interface == IFACE:
            env = json.loads(msg.body[0])
            if env["type"] == "task.finished":
                finished[env["task_id"]] = env["payload"]

    bus.add_message_handler(on_event)
    await call(bus, "Hello", {"client": {"kind": "test"}, "protocol": [2, 1]})
    await call(bus, "Attach", {"scope": "all", "after_seq": 0})
    cfg = await call(bus, "GetConfig")
    await call(bus, "UpdateConfig", {"revision": cfg["revision"], "config": {
        "active": "openai", "providers": {"openai": {"url": url, "model": "mock-1"}}}})
    models = await call(bus, "ListModels", {"provider": "openai", "url": url})
    # Another local process asking Mei to list models somewhere else must not get the key sent there.
    sent_before = SEEN_AUTH.count(f"Bearer {KEY}")
    deputy = await call(bus, "ListModels", {"provider": "openai", "url": f"http://localhost:{port}/v1/chat/completions"})
    key_sent_elsewhere = SEEN_AUTH.count(f"Bearer {KEY}") - sent_before
    setup = await call(bus, "SetupStatus")
    test = await call(bus, "TestProvider", {}, timeout=60)
    ok = await turn(bus, finished, "hello")
    failed = await turn(bus, finished, "please fail", ok["conversation_id"])
    failed_in_stream = await turn(bus, finished, "please fail inside the stream", ok["conversation_id"])
    conversation = await call(bus, "GetConversation", {"conversation_id": ok["conversation_id"]})
    logs = await call(bus, "GetLogs", {"after": 0})
    await asyncio.sleep(0.5)  # let the monitor catch the last replies
    server.shutdown()

    def leaks_in(messages: list[Message]) -> list[str]:
        return [f"{m.message_type.name} {m.sender}->{m.destination} {m.member or ''}" for m in messages
                if KEY.encode() in repr(m.body).encode() or KEY in json.dumps(m.body, default=str)]

    mei = monitor.mei_messages()
    print(json.dumps({
        "mei_messages": len(mei),
        "mei_signals": sum(m.message_type == MessageType.SIGNAL for m in mei),
        "leaks": leaks_in(mei),
        # Keyring traffic included: keys cross the bus encrypted, so the key is in no message at all.
        "leaks_anywhere": leaks_in(monitor.messages),
        "bus_messages": len(monitor.messages),
        "deputy_error": deputy.get("error", ""),
        "key_sent_elsewhere": key_sent_elsewhere,
        "failed_in_stream_error": failed_in_stream["finished"].get("error", ""),
        "key_used_upstream": SEEN_AUTH.count(f"Bearer {KEY}"),
        "models": models["models"],
        "setup_has_key": next(s for s in setup["steps"] if s["id"] == "models")["has_key"],
        "test_ok": test["ok"],
        "turn_ok": ok["finished"]["state"],
        "failed_error": failed["finished"].get("error", ""),
        "key_in_stored_history": KEY in json.dumps(conversation),
        "key_in_logs": KEY in json.dumps(logs),
    }))


asyncio.run(main())
sys.exit(0)
