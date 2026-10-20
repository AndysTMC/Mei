"""Stage 1 end-to-end: nested GNOME Shell + dev-built extension + D-Bus-activated runtime + a mock
OpenAI-compatible provider. Run through scripts/e2e-stage1.sh, which prepares a private session.

Checks the Stage 1 acceptance criteria against what the popup actually shows (read through the
dev-build test hooks), not just against runtime state.
"""

import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from dbus_fast import BusType, Message, MessageType
from dbus_fast.aio import MessageBus

OUT, PORT = sys.argv[1], int(sys.argv[2])
REQUESTS = os.path.join(OUT, "provider-requests.jsonl")
WORDS = [f"w{i:02d}" for i in range(60)]
PIECES = ["Mock reply:"] + [" " + w for w in WORDS]
REPLY = "".join(PIECES)
DELAY_S = 0.08
NEXT_BUTTON = (920, 665)  # in the setup assistant, in the nested Shell's 1280×800 screen
CHOOSE_PROVIDER_BUTTON = (842, 287)  # "Choose…" on the Models step
BACK_BUTTON = (342, 135)  # the header's back arrow
MODEL_PROVIDER_ROW = (460, 412)  # "Model provider" on Settings' main page


class MockProvider(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))))
        with open(REQUESTS, "a") as f:
            f.write(json.dumps({"t": time.time(), "last": body["messages"][-1]["content"],
                                "messages": len(body["messages"]), "model": body["model"]}) + "\n")
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        try:
            for piece in PIECES:
                self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}).encode() + b"\n\n")
                self.wfile.flush()
                time.sleep(DELAY_S)
            self.wfile.write(b"data: [DONE]\n\n")
        except (BrokenPipeError, ConnectionResetError):
            pass  # the runtime was killed mid-stream

    def log_message(self, *_args):
        pass


def requests() -> list[dict]:
    return [json.loads(line) for line in open(REQUESTS)] if os.path.exists(REQUESTS) else []


class Harness:
    def __init__(self, bus: MessageBus) -> None:
        self.bus = bus
        self.results: dict = {}
        self.shell: subprocess.Popen | None = None

    async def _call(self, dest, path, iface, member, sig="", body=None):
        reply = await self.bus.call(Message(destination=dest, path=path, interface=iface, member=member,
                                            signature=sig, body=body or []))
        if reply.message_type == MessageType.ERROR:
            raise RuntimeError(f"{reply.error_name}: {reply.body}")
        return reply.body

    async def hook(self, member: str, arg: str | None = None):
        body = await self._call("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev", member,
                                "s" if arg is not None else "", [arg] if arg is not None else [])
        return json.loads(body[0]) if member == "State" else None

    async def click(self, x: int, y: int) -> None:
        await self._call("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev", "Click", "ii", [x, y])
        await asyncio.sleep(0.8)  # the step transition

    async def runtime(self, member: str, args: dict) -> dict:
        body = await self._call("com.andystmc.Mei1", "/com/andystmc/Mei1", "com.andystmc.Mei1.Runtime",
                                member, "s", [json.dumps(args)])
        return json.loads(body[0])

    async def state(self) -> dict:
        return await self.hook("State")

    async def until(self, pred, timeout: float, what: str) -> dict:
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                last = await self.state()
                if pred(last):
                    return last
            except RuntimeError:
                pass  # hooks not exported yet (Shell starting, extension re-enabling)
            await asyncio.sleep(0.1)
        raise AssertionError(f"timed out waiting for {what}; last state: {json.dumps(last)[:1500]}")

    def start_shell(self) -> None:
        log = open(os.path.join(OUT, "shell.log"), "a")
        self.shell = subprocess.Popen(["gnome-shell", "--devkit", "--wayland", "--no-x11"], stdout=log, stderr=log)

    def stop_shell(self) -> None:
        if self.shell:
            self.shell.send_signal(signal.SIGTERM)
            self.shell.wait(timeout=20)

    def check(self, name: str, ok: bool, detail="") -> None:
        self.results[name] = {"ok": bool(ok), **({"detail": detail} if detail else {})}


def shows_reply_prefix(state: dict, min_len: int) -> int:
    best = 0
    for text in state["shown"]:
        t = text.strip()
        if REPLY.startswith(t) and len(t) >= min_len:
            best = max(best, len(t))
    return best


def stream_len(state: dict) -> int:
    s = state["controller"]["stream"]
    return len(s["text"]) if s else 0


async def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), MockProvider)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    h = Harness(bus)
    h.start_shell()
    try:
        # 1. The extension starts the runtime by D-Bus activation. Settings live in the runtime: configure
        #    it the way Settings would, and the popup picks the change up from config.changed.
        await h.until(lambda s: s["controller"]["status"] == "connected", 60, "the extension to connect")

        # 0. First run: setup was never offered, so the extension opens Settings, and Settings opens on
        #    the setup assistant and marks it offered.
        deadline = time.monotonic() + 40
        while not (setup := await h.runtime("SetupStatus", {}))["offered"] and time.monotonic() < deadline:
            await asyncio.sleep(0.25)
        st = await h.state()
        h.check("setup_opens_on_first_run", setup["offered"] and not setup["completed"]
                and st["controller"]["setupOffered"], {"offered": setup["offered"]})
        await asyncio.sleep(2.0)  # let the window finish drawing
        await h.hook("Screenshot", os.path.join(OUT, "setup-1-service.png"))
        for name in ("2-models", "3-privacy", "4-shortcuts", "5-done"):
            await h.click(*NEXT_BUTTON)
            await h.hook("Screenshot", os.path.join(OUT, f"setup-{name}.png"))
            if name == "2-models":  # "Choose…" opens the provider page on top of setup; Back returns
                await h.click(*CHOOSE_PROVIDER_BUTTON)
                await h.hook("Screenshot", os.path.join(OUT, "provider-page.png"))
                await h.click(*BACK_BUTTON)
        await h.click(*NEXT_BUTTON)  # Finish
        await asyncio.sleep(1.0)
        setup = await h.runtime("SetupStatus", {})
        h.check("setup_finishes_from_the_assistant", setup["completed"] and setup["skipped"] == [],
                {"completed": setup["completed"], "skipped": setup["skipped"]})
        await h.hook("Screenshot", os.path.join(OUT, "settings.png"))

        cfg = await h.runtime("GetConfig", {})
        url = f"http://127.0.0.1:{PORT}/v1/chat/completions"
        await h.runtime("UpdateConfig", {"revision": cfg["revision"], "config": {
            "active": "custom", "providers": {"custom": {"url": url, "model": "mock-1"}}}})
        st = await h.until(lambda s: s["controller"]["provider"] == "custom", 10, "the popup to see the new provider")
        cfg = await h.runtime("GetConfig", {})
        h.check("connected_and_configured", cfg["config"]["active"] == "custom"
                and cfg["config"]["providers"]["custom"]["url"] == url
                and st["controller"]["provider"] == "custom", cfg["config"])

        await h.click(*MODEL_PROVIDER_ROW)  # Settings is still open on its main page
        await h.hook("Screenshot", os.path.join(OUT, "provider-custom.png"))
        await h.click(*BACK_BUTTON)

        # 1b. The default shortcut (Super+Alt+M) opens the popup from anywhere and closes it again.
        await h.hook("PressOpenShortcut")
        opened = (await h.until(lambda s: s["popup"]["open"], 5, "the shortcut to open the popup"))["popup"]["open"]
        await h.hook("PressOpenShortcut")
        await asyncio.sleep(0.5)
        h.check("shortcut_toggles_popup", opened and not (await h.state())["popup"]["open"])

        # 2. Stream with the popup open, close it mid-stream, reopen: the partial answer is there at once.
        await h.hook("Popup", "open")
        await h.hook("Popup", "expand")
        await h.hook("Send", "first question")
        await h.until(lambda s: stream_len(s) > 30, 20, "streaming to start")
        await h.hook("Popup", "close")
        await asyncio.sleep(1.0)
        await h.hook("Popup", "open")
        st = await h.state()
        shown = shows_reply_prefix(st, 31)
        h.check("partial_shown_at_once_after_reopen", shown > 30 and st["controller"]["streaming"],
                f"{shown} chars shown immediately")
        st = await h.until(lambda s: not s["controller"]["streaming"], 30, "the first reply to finish")
        h.check("completed_reply_shown", any(t.strip() == REPLY for t in st["shown"]))
        await asyncio.sleep(0.5)
        await h.hook("Screenshot", os.path.join(OUT, "popup-expanded.png"))

        # 3. Disable and re-enable the extension mid-stream: the reattached view ends with the whole reply.
        await h.hook("Send", "second question")
        await h.until(lambda s: stream_len(s) > 30, 20, "the second reply to start")
        subprocess.run(["gnome-extensions", "disable", "mei@andystmc.com"], check=True)
        await asyncio.sleep(1.5)
        subprocess.run(["gnome-extensions", "enable", "mei@andystmc.com"], check=True)
        st = await h.until(lambda s: s["controller"]["status"] == "connected", 30, "reconnect after re-enable")
        await asyncio.sleep(1.0)
        h.check("setup_not_reopened", not (await h.state())["controller"]["setupOffered"])
        await h.hook("Popup", "open")
        await h.hook("Popup", "expand")
        await h.hook("Popup", "load-latest")
        st = await h.until(lambda s: len(s["controller"]["messages"]) >= 4 and not s["controller"]["streaming"],
                           30, "the second reply after re-enable")
        msgs = st["controller"]["messages"]
        h.check("reenable_shows_complete_reply", [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
                and msgs[-1]["content"] == REPLY and any(t.strip() == REPLY for t in st["shown"]))

        # 4. Kill the runtime mid-stream: it comes back, the turn is INTERRUPTED with its draft shown, and
        #    the provider is not called again until the user presses ↻.
        await h.hook("Send", "third question")
        await h.until(lambda s: stream_len(s) > 60, 20, "the third reply to start")
        await asyncio.sleep(2.2)  # past the runtime's 2 s draft checkpoint
        pid = (await h.runtime("Hello", {"client": {"kind": "e2e"}, "protocol": [2, 1]}))["pid"]
        before = len(requests())
        os.kill(pid, signal.SIGKILL)
        st = await h.until(lambda s: s["controller"]["interrupted"] is not None and s["controller"]["status"] == "connected",
                           30, "the interrupted draft")
        draft = st["controller"]["interrupted"]["text"]
        h.check("interrupted_draft_shown", REPLY.startswith(draft) and len(draft) > 20
                and any("(interrupted" in t for t in st["shown"]), f"draft {len(draft)} chars")
        await asyncio.sleep(1.0)
        h.check("no_automatic_resend", len(requests()) == before, f"{len(requests())} provider requests")
        await h.hook("Popup", "reload-draft")
        st = await h.until(lambda s: s["controller"]["interrupted"] is None and not s["controller"]["streaming"]
                           and s["controller"]["messages"][-1]["role"] == "assistant", 30, "the resumed reply")
        h.check("resume_completes", st["controller"]["messages"][-1]["content"] == REPLY
                and len(requests()) == before + 1)
        h.check("history_sent_to_provider", requests()[-1]["messages"] == 5)  # 3 user + 2 assistant
        await h.hook("Popup", "collapse")
        await asyncio.sleep(1.0)
        st = await h.state()
        h.check("compact_shows_the_last_reply", not st["popup"]["expanded"] and any(t.strip() == REPLY for t in st["shown"]))
        await h.hook("Screenshot", os.path.join(OUT, "popup-compact.png"))
    except AssertionError as e:
        h.results["error"] = str(e)
    finally:
        h.stop_shell()
        server.shutdown()
        subprocess.run(["pkill", "-f", "-m", "mei serve"], check=False)
    print(json.dumps(h.results, indent=1))
    return 0 if h.results and all(v.get("ok") for k, v in h.results.items() if k != "error") \
        and "error" not in h.results else 1


sys.exit(asyncio.run(main()))
