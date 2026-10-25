"""End-to-end: nested GNOME Shell + dev-built extension + D-Bus-activated runtime + a mock
OpenAI-compatible provider (chat) and the scripted provider (agent). Run through
scripts/e2e-stage1.sh, which prepares a private session and home.

Checks the Stage 1 acceptance criteria, and the Stage 3 approval card and dark-mode slice, against
what the popup actually shows (read through the dev-build test hooks), not just runtime state.
"""

import asyncio
import json
import os
import re
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
# Points in Settings' window, as they are with its top-left corner at WINDOW_AT in the nested Shell's
# 1280×800 screen; `click_window` moves them to wherever the Shell placed the window.
WINDOW_AT = (320, 112)
NEXT_BUTTON = (920, 665)  # in the setup assistant
CHOOSE_PROVIDER_BUTTON = (842, 287)  # "Choose…" on the Models step
BACK_BUTTON = (342, 135)  # the header's back arrow
MODEL_PROVIDER_ROW = (460, 412)  # "Model provider" on Settings' main page
MEMORY_ROW = (460, 463)  # "Memory", the row under it
VOICE_ROW = (460, 514)  # "Voice", under Memory


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
        self.retried_clicks: list[str] = []

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

    async def click_window(self, x: int, y: int) -> None:
        """Click a point in the focused window (Settings), measured with it at WINDOW_AT."""
        frame = (await self.state())["window"]
        if frame is None:
            raise RuntimeError("no focused window to click in")
        await self.click(x + frame["x"] - WINDOW_AT[0], y + frame["y"] - WINDOW_AT[1])

    async def scroll(self, x: int, y: int, steps: int) -> None:
        await self._call("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev", "Scroll", "iii", [x, y, steps])
        await asyncio.sleep(0.5)  # the scroll animation

    async def runtime(self, member: str, args: dict) -> dict:
        body = await self._call("com.andystmc.Mei1", "/com/andystmc/Mei1", "com.andystmc.Mei1.Runtime",
                                member, "s", [json.dumps(args)])
        return json.loads(body[0])

    async def state(self) -> dict:
        return await self.hook("State")

    async def press(self, label: str) -> bool:
        """Click the popup's button with this label where it is on screen, once it is on top (a
        card may still be fading in or scrolling into view). A click the nested Shell dropped on the
        way in is tried again, and noted in `self.retried_clicks`. False if the button never took
        a click, and why is in `self.results["clicks"]`."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            body = await self._call("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev", "ClickButton", "s",
                                    [label])
            if not body[0]:
                await asyncio.sleep(0.2)
                continue
            click = (await self.state())["clicks"][-1]
            if not click["picked"]:  # not on top yet
                await asyncio.sleep(0.2)
                continue
            for _ in range(15):
                await asyncio.sleep(0.1)
                if (await self.state())["clicks"][-1]["clicked"]:
                    await asyncio.sleep(0.4)
                    return True
            self.retried_clicks.append(label)
        self.results.setdefault("clicks", (await self.state())["clicks"])
        return False

    async def use_fake(self, script: list[dict], delay_ms: int = 10, **options) -> None:
        """Switch to the scripted provider, keeping every other setting."""
        cfg = await self.runtime("GetConfig", {})
        config = cfg["config"]
        providers = {**config["providers"], "fake": {"options": {"script": script, "delay_ms": delay_ms, **options}}}
        await self.runtime("UpdateConfig", {"revision": cfg["revision"],
                                            "config": {**config, "active": "fake", "providers": providers}})
        await self.until(lambda s: s["controller"]["provider"] == "fake", 10, "the popup to see the scripted provider")

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
        """Headless, with a virtual 1280×800 screen: no window in the real session, whose pointer
        would otherwise reach the Shell under test and move the hooks' clicks off their targets."""
        log = open(os.path.join(OUT, "shell.log"), "a")
        self.shell = subprocess.Popen(["gnome-shell", "--headless", "--virtual-monitor", "1280x800", "--wayland",
                                       "--no-x11"], stdout=log, stderr=log)

    def launch(self, app: str, *args: str) -> subprocess.Popen:
        """A test app (tests/e2e/apps) on the nested Shell's display."""
        display = re.findall(r"Using Wayland display name '([^']+)'", open(os.path.join(OUT, "shell.log")).read())[-1]
        env = {**os.environ, "WAYLAND_DISPLAY": display, "GDK_BACKEND": "wayland"}
        log = open(os.path.join(OUT, f"{app}.log"), "a")
        return subprocess.Popen(["/usr/bin/python3", os.path.join(os.path.dirname(__file__), "apps", f"{app}.py"), *args],
                                env=env, stdout=log, stderr=log)

    async def drag_onto_mei(self, payload: str) -> dict:
        """Drag from a test app onto Mei's panel button and let go; the state once the drop is in."""
        app = self.launch("dragsource", payload)
        try:
            st = await self.until(lambda s: (s["window"] or {}).get("title") == "Mei drag source", 15, "the drag source")
            await asyncio.sleep(0.5)
            w, b = st["window"], st["drop"]["button"]
            start = (w["x"] + w["width"] // 2, w["y"] + w["height"] // 2)
            for _ in range(3):  # a press on its way in can be lost (as in `press`); a person presses again
                await self._call("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev", "Drag", "iiii",
                                 [*start, b["x"] + b["width"] // 2, b["y"] + b["height"] // 2])
                try:
                    return await self.until(lambda s: s["popup"]["open"] and s["controller"]["attachment"], 5,
                                            "the drop to attach")
                except AssertionError:
                    self.retried_clicks.append("drag onto Mei")
            raise AssertionError("nothing reached Mei from three drags")
        finally:
            app.terminate()
            app.wait(5)

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
        # Clicks sent while the Shell's startup animation plays are lost, and so is the pointer that sent them.
        await h.until(lambda s: not s["startingUp"], 60, "the Shell to finish starting up")

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
        for name in ("2-models", "3-approvals", "4-memory", "5-voice", "6-computer", "7-privacy", "8-shortcuts", "9-done"):
            await h.click_window(*NEXT_BUTTON)
            await h.hook("Screenshot", os.path.join(OUT, f"setup-{name}.png"))
            if name == "2-models":  # "Choose…" opens the provider page on top of setup; Back returns
                await h.click_window(*CHOOSE_PROVIDER_BUTTON)
                await h.hook("Screenshot", os.path.join(OUT, "provider-page.png"))
                await h.click_window(*BACK_BUTTON)
        await h.click_window(*NEXT_BUTTON)  # Finish
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

        await h.click_window(*MODEL_PROVIDER_ROW)  # Settings is still open on its main page
        await h.hook("Screenshot", os.path.join(OUT, "provider-custom.png"))
        await h.click_window(*BACK_BUTTON)
        await h.click_window(*MEMORY_ROW)
        await h.hook("Screenshot", os.path.join(OUT, "memory-page.png"))
        await h.click_window(*BACK_BUTTON)
        await h.click_window(*VOICE_ROW)
        await asyncio.sleep(0.5)
        await h.hook("Screenshot", os.path.join(OUT, "voice-page.png"))
        for part in (2, 3):  # the rest of the page
            await h.scroll(640, 450, 5)
            await h.hook("Screenshot", os.path.join(OUT, f"voice-page-{part}.png"))
        await h.click_window(*BACK_BUTTON)

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
        h.check("history_sent_to_provider", requests()[-1]["messages"] == 6)  # Mei's system prompt, 3 user, 2 assistant
        await h.hook("Popup", "collapse")
        await asyncio.sleep(1.0)
        st = await h.state()
        h.check("compact_shows_the_last_reply", not st["popup"]["expanded"] and any(t.strip() == REPLY for t in st["shown"]))
        await h.hook("Screenshot", os.path.join(OUT, "popup-compact.png"))

        # 5. Stage 3: an agent task needs an approval; it takes over the input area, the person allows it
        #    in the small popup, and it goes away; the approval is accepted because it comes from the
        #    Shell process itself. One request, one reply.
        await h.use_fake([
            {"text": "I'll tidy that.", "tool_calls": [{"name": "fs_trash", "arguments": {"path": "~/Music/old.txt"}}]},
            {"tool_calls": [{"name": "task_finish", "arguments": {"summary": "Moved old.txt to the trash."}}]}])
        await h.hook("Popup", "new")
        await h.hook("Popup", "open")
        await h.hook("Popup", "expand")
        await h.hook("Send", "tidy up my files")
        st = await h.until(lambda s: "approval" in s["controller"]["timeline"], 30, "the approval card")
        h.check("approval_card_shown", st["controller"]["waiting"] and "Mei wants to" in st["shown"]
                and "Move ~/Music/old.txt to the trash" in st["shown"] and "Ask" not in st["shown"], st["shown"][-10:])
        await asyncio.sleep(0.5)
        await h.hook("Screenshot", os.path.join(OUT, "approval-card.png"))
        await h.hook("Popup", "collapse")  # answered in the small popup, where it used to stay after a click
        await asyncio.sleep(0.6)
        await h.hook("Screenshot", os.path.join(OUT, "approval-compact.png"))
        clicked = await h.press("Allow once")
        st = await h.until(lambda s: "outcome" in s["controller"]["timeline"], 30, "the approved task to finish")
        await asyncio.sleep(0.5)
        st = await h.state()
        trashed = os.path.join(OUT, "data", "Trash/files/old.txt")  # the trash lives in XDG_DATA_HOME
        h.check("approved_from_the_popup", clicked and not os.path.exists(os.path.join(OUT, "home/Music/old.txt"))
                and os.path.exists(trashed) and not st["controller"]["waiting"] and "Allow once" not in st["shown"]
                and "Ask" in st["shown"],
                {"clicks retried": h.retried_clicks} if h.retried_clicks else None)
        await h.hook("Screenshot", os.path.join(OUT, "approved-compact.png"))
        await h.hook("Popup", "expand")
        await asyncio.sleep(0.6)
        shown = (await h.state())["shown"]
        # One reply to the request; what Mei said on the way ("I'll tidy that.") is behind Steps.
        h.check("one_reply_per_request", shown.count("tidy up my files") == 1
                and any("Moved old.txt to the trash" in t for t in shown) and not any("I'll tidy that" in t for t in shown),
                shown[-10:])
        await h.hook("Screenshot", os.path.join(OUT, "one-reply.png"))
        await h._call("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev", "HoverButton", "s", ["Steps"])
        await asyncio.sleep(0.4)
        await h.hook("Screenshot", os.path.join(OUT, "footer-hover.png"))
        await h._call("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev", "ClickNamed", "s", ["Steps"])
        await asyncio.sleep(0.6)
        await h.hook("Screenshot", os.path.join(OUT, "footer-steps.png"))

        # 6. The dark-mode slice through the real Shell bridge: nothing it touches needs a card, and Mei
        #    checks both criteria itself (the setting, and a Files window the Shell reports).
        await h.use_fake([
            {"tool_calls": [{"name": "plan_update", "arguments": {"criteria": [
                {"text": "Dark mode is on", "check": {"type": "setting_equals", "schema": "org.gnome.desktop.interface",
                                                      "key": "color-scheme", "value": "prefer-dark"}},
                {"text": "Files is open", "check": {"type": "window_present", "app_id": "org.gnome.Nautilus"}}]}}]},
            {"tool_calls": [
                {"name": "settings_set", "arguments": {"schema": "org.gnome.desktop.interface", "key": "color-scheme",
                                                       "value": "prefer-dark"}},
                {"name": "apps_launch", "arguments": {"app_id": "org.gnome.Nautilus"}}]},
            {"tool_calls": [{"name": "task_finish", "arguments": {"summary": "Dark mode is on and Files is open.",
                                                                   "criteria": [{"index": 0, "status": "met"},
                                                                                {"index": 1, "status": "met"}]}}]}])
        subprocess.run(["/usr/bin/gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "default"], check=True)
        await h.hook("Popup", "new")
        await h.hook("Send", "Switch to dark mode and open Files")
        st = await h.until(lambda s: "outcome" in s["controller"]["timeline"], 60, "the dark-mode task to finish")
        conv = await h.runtime("GetConversation", {"conversation_id": st["controller"]["current"]})
        outcome = conv["tasks"][-1]["outcome"]
        h.check("dark_mode_slice_verified", outcome["kind"] == "outcome_verified"
                and "approval" not in st["controller"]["timeline"], outcome)
        await asyncio.sleep(1.0)
        await h.hook("Popup", "open")
        await h.hook("Screenshot", os.path.join(OUT, "dark-mode-slice.png"))
        await h._call("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev", "ClickNamed", "s", ["Checks"])
        await asyncio.sleep(0.6)
        await h.hook("Screenshot", os.path.join(OUT, "footer-checks.png"))

        # 7. Stage 4: a task that outlasts an extension restart. The history list shows it working; when
        #    it finishes, a notification says so (the popup stays closed), and clicking it opens the chat.
        slow = "Still working on it, one slow piece at a time. " * 4  # 25 chunks, one a second
        await h.use_fake([{"text": slow}], delay_ms=1000)
        await h.hook("Popup", "new")
        await h.hook("Send", "take your time with this one")
        conv = (await h.until(lambda s: s["controller"]["current"], 10, "the long task to start"))["controller"]["current"]
        await h.hook("Popup", "close")
        st = await h.until(lambda s: any(i["id"] == conv and i["active"] == "Working…" for i in s["controller"]["history"]),
                           10, "the task in the history list")
        h.check("history_lists_the_task_in_progress", st["controller"]["busy"])
        subprocess.run(["gnome-extensions", "disable", "mei@andystmc.com"], check=True)
        await asyncio.sleep(1.5)
        subprocess.run(["gnome-extensions", "enable", "mei@andystmc.com"], check=True)
        await h.until(lambda s: s["controller"]["status"] == "connected" and s["controller"]["busy"], 30,
                      "the re-enabled extension to see the task still working")
        st = await h.until(lambda s: s["controller"]["notice"] is not None, 60, "the completion notice")
        notice = st["controller"]["notice"]
        h.check("long_task_notifies_after_restart", notice["conversationId"] == conv and notice["title"] == "Mei finished"
                and not st["popup"]["open"] and any(n["title"] == "Mei finished" for n in st["notifications"]), notice)
        await h.hook("Screenshot", os.path.join(OUT, "notification.png"))
        await h.hook("Popup", "activate-notice")
        st = await h.until(lambda s: s["popup"]["open"] and s["controller"]["current"] == conv
                           and any(t.strip() == slow.strip() for t in s["shown"]), 10, "the notification to open the chat")
        h.check("notification_opens_the_chat", not any(n["title"] == "Mei finished" and n["body"].startswith("take your")
                                                       for n in st["notifications"]), st["notifications"])
        await h.hook("Popup", "close")

        # 8. A task that finishes while the extension is off: the runtime notifies through the desktop.
        await h.use_fake([{"text": "Done while you were away. " * 3}], delay_ms=300)
        await h.hook("Popup", "new")
        await h.hook("Send", "finish this while I'm away")
        conv = (await h.until(lambda s: s["controller"]["current"], 10, "the task to start"))["controller"]["current"]
        subprocess.run(["gnome-extensions", "disable", "mei@andystmc.com"], check=True)
        deadline = time.monotonic() + 30
        while (state := (await h.runtime("GetConversation", {"conversation_id": conv}))["tasks"][-1]["state"]) \
                != "COMPLETED" and time.monotonic() < deadline:
            await asyncio.sleep(0.25)
        subprocess.run(["gnome-extensions", "enable", "mei@andystmc.com"], check=True)
        st = await h.until(lambda s: s["controller"]["status"] == "connected", 30, "reconnect after re-enable")
        title = (await h.runtime("GetConversation", {"conversation_id": conv}))["conversation"]["title"]
        h.check("runtime_notifies_while_detached", state == "COMPLETED" and any(
            n["title"] == "Mei finished" and n["body"] == title for n in st["notifications"]), st["notifications"])

        # 9. "Ask about this": the shortcut opens a new chat with the focused window and the selected
        #    text attached; the chip shows it, and the message carries it to the runtime.
        await h.use_fake([{"text": "That's a line of release notes."}])
        selected = "Version 2 drops the legacy importer."
        await h.hook("SetPrimarySelection", selected)
        await h.hook("PressAskShortcut")
        st = await h.until(lambda s: s["popup"]["open"] and s["controller"]["attachment"] is not None, 10,
                           "the shortcut to attach the selection")
        attached = st["controller"]["attachment"]
        chip = next((t for t in st["shown"] if t.startswith("About: ")), "")
        await h.hook("Screenshot", os.path.join(OUT, "ask-about-this.png"))
        await h.hook("Send", "what does this mean?")
        st = await h.until(lambda s: s["controller"]["current"] and s["controller"]["attachment"] is None
                           and not s["controller"]["streaming"], 20, "the question about the selection")
        conv = await h.runtime("GetConversation", {"conversation_id": st["controller"]["current"]})
        sent = conv["messages"][0]
        h.check("ask_about_this_attaches_the_selection", attached["text"] == selected and selected[:20] in chip
                and sent["content"] == "what does this mean?" and sent["metadata"]["attachment"]["text"] == selected
                and conv["tasks"][-1]["state"] == "COMPLETED", {"chip": chip, "attached": attached})

        # 9b. Drag and drop (decision 0027): a file dragged from an app onto Mei's button is attached to
        #     the next message; the model gets its path, and, as the person pointed at it, may read it and
        #     send what it holds to a cloud model under "Files I point to", with no card. Text dropped
        #     the same way is attached as content others wrote.
        await h.hook("Popup", "new")
        await h.hook("Popup", "close")
        note = os.path.join(OUT, "home", "Documents", "shopping list.txt")
        os.makedirs(os.path.dirname(note), exist_ok=True)
        with open(note, "w") as f:
            f.write("Eggs, milk, DROPPED-NOTE-7.\n")
        log = os.path.join(OUT, "fake-drop-calls.jsonl")
        await h.use_fake([{"tool_calls": [{"name": "fs_read_text", "arguments": {"path": note}}]},
                          {"text": "Eggs and milk."}], cloud=True, call_log=log)
        st = await h.drag_onto_mei(note)
        attached, drop = st["controller"]["attachment"], st["drop"]
        chip = next((t for t in st["shown"] if t.startswith("Attached: ")), "")
        await h.hook("Screenshot", os.path.join(OUT, "dropped-file.png"))
        await h.hook("Send", "what's on this list?")
        st = await h.until(lambda s: s["controller"]["current"] and s["controller"]["attachment"] is None
                           and not s["controller"]["streaming"], 20, "the question about the dropped file")
        conv = await h.runtime("GetConversation", {"conversation_id": st["controller"]["current"]})
        calls = [json.loads(line) for line in open(log)] if os.path.exists(log) else []
        seen = [t["content"] for c in calls for t in c.get("turns", [])]
        h.check("dropped_file_attaches_and_is_read", attached.get("paths") == [note] and chip == "Attached: shopping list.txt"
                and drop["state"] == "idle" and conv["messages"][0]["metadata"]["attachment"]["paths"] == [note]
                and any(json.dumps(note) in t and 'kind="files"' in t for t in seen)
                and any("DROPPED-NOTE-7" in t for t in seen) and conv["tasks"][-1]["state"] == "COMPLETED",
                {"attached": attached, "chip": chip, "drop": drop, "task": conv["tasks"][-1]["state"]})
        await h.hook("Popup", "close")
        await h.use_fake([{"text": "It's a sentence."}])
        st = await h.drag_onto_mei("Some words from a web page")
        attached = st["controller"]["attachment"]
        h.check("dropped_text_attaches_as_untrusted", attached["kind"] == "text"
                and attached["text"] == "Some words from a web page"
                and "About: “Some words from a web page”" in st["shown"], attached)
        await h.hook("Popup", "new")
        await h.hook("Popup", "close")

        # 10. Memory: "remember that…" is saved as the person's own fact and shown in the conversation;
        #     Undo there forgets it.
        fact = "Invoices go in Documents/Invoices"
        await h.use_fake([{"tool_calls": [{"name": "memory_save", "arguments": {"text": fact}}]}, {"text": "Got it."}])
        await h.hook("Popup", "new")
        await h.hook("Popup", "open")
        await h.hook("Popup", "expand")
        await h.hook("Send", "Remember that my invoices go in Documents/Invoices")
        st = await h.until(lambda s: "memory" in s["controller"]["timeline"] and not s["controller"]["streaming"], 30,
                           "the memory card")
        saved = (await h.runtime("Memories", {}))["memories"]
        h.check("memory_saved_and_shown", "Remembered" in st["shown"] and fact in st["shown"]
                and [(m["text"], m["provenance"], m["status"]) for m in saved] == [(fact, "user_stated", "active")],
                {"saved": saved, "shown": st["shown"][-6:]})
        await h.hook("Screenshot", os.path.join(OUT, "memory-card.png"))
        clicked = await h.press("Undo")
        st = await h.until(lambda s: "memory" not in s["controller"]["timeline"], 10, "Undo to forget it")
        h.check("memory_undone_from_the_popup", clicked and (await h.runtime("Memories", {}))["memories"] == [])

        # 11. The Shell itself restarts mid-task (as after a crash): the task keeps running in the runtime,
        #     and the new Shell's extension notifies when it finishes.
        slow = "Still working through a Shell restart, one slow piece at a time. " * 4  # 34 chunks, one a second
        await h.use_fake([{"text": slow}], delay_ms=1000)
        await h.hook("Popup", "new")
        await h.hook("Send", "keep going while the Shell restarts")
        conv = (await h.until(lambda s: s["controller"]["current"], 10, "the task to start"))["controller"]["current"]
        h.stop_shell()
        h.start_shell()
        await h.until(lambda s: s["controller"]["status"] == "connected" and s["controller"]["busy"]
                      and not s["startingUp"], 60, "the restarted Shell to see the task still working")
        st = await h.until(lambda s: (s["controller"]["notice"] or {}).get("conversationId") == conv, 90,
                           "the notice after the Shell restart")
        task = (await h.runtime("GetConversation", {"conversation_id": conv}))["tasks"][-1]
        h.check("task_survives_a_shell_restart_and_notifies", task["state"] == "COMPLETED"
                and st["controller"]["notice"]["title"] == "Mei finished"
                and any(n["title"] == "Mei finished" for n in st["notifications"]), st["controller"]["notice"])

        # 12. Voice (decision 0026): Super+Alt+Space listens with the popup closed (the top bar shows
        #     it); the question (from a file standing in for the microphone) becomes a spoken request;
        #     the popup opens with the answer, which is spoken (captured to a file); and Mei listens on
        #     afterwards until the shortcut, pressed with nothing said, stops it.
        models = os.environ.get("MEI_VOICE_MODELS", "")
        if models and os.path.exists(os.path.join(models, "sherpa-onnx-streaming-zipformer-en-kroko-2025-08-06")):
            import numpy as np
            from mei.voice import local
            piper = local.piper(__import__("pathlib").Path(models))
            # Two sentences, so "weather" is heard for a while before the person stops talking.
            question = (await piper.synthesize("What's the weather like tomorrow? I'm going out for a long walk.")).samples
            np.concatenate([np.zeros(8000, np.float32), question, np.zeros(16000 * 60, np.float32)]).astype(
                np.float32).tofile(os.environ["MEI_VOICE_SOURCE_FILE"])
            await h.use_fake([{"text": "It will be sunny tomorrow. Around eighteen degrees."}])
            cfg = await h.runtime("GetConfig", {})
            # A short pause before sending, so the scenario doesn't wait out the 8 s default.
            config = {**cfg["config"], "voice": {**cfg["config"].get("voice", {}), "enabled": True, "end_pause_ms": 700}}
            await h.runtime("UpdateConfig", {"revision": cfg["revision"], "config": config})
            await h.until(lambda s: s["controller"]["voice"]["state"] == "idle", 90, "voice to be ready")
            await h.hook("Popup", "new")
            await h.hook("Popup", "close")
            await h.hook("PressVoiceShortcut")
            st = await h.until(lambda s: s["controller"]["voice"]["state"] == "listening"
                               and "weather" in s["controller"]["voice"]["transcript"].lower(), 30, "the question heard")
            closed_while_listening = not st["popup"]["open"]
            await h.hook("Screenshot", os.path.join(OUT, "voice-listening-top-bar.png"))
            st = await h.until(lambda s: s["controller"]["voice"]["state"] == "speaking", 60, "the spoken answer")
            opened_with_answer = st["popup"]["open"]
            st = await h.until(lambda s: s["controller"]["current"] and s["controller"]["voice"]["state"] == "listening"
                               and len(s["controller"]["messages"]) >= 2, 60, "listening again after the answer")
            await h.hook("Screenshot", os.path.join(OUT, "voice-listening.png"))
            conv = await h.runtime("GetConversation", {"conversation_id": st["controller"]["current"]})
            user = conv["messages"][0]
            played = os.path.getsize(os.environ["MEI_VOICE_SINK_FILE"]) / 4 / 16000
            await h.hook("PressEnter")  # the popup is open: Enter ends the conversation (decision 0028)
            await h.until(lambda s: s["controller"]["voice"]["state"] == "idle", 20, "Enter to end the conversation")
            h.check("voice_question_answered_out_loud", closed_while_listening and opened_with_answer
                    and user["metadata"].get("source") == "voice"
                    and user["content"].lower().startswith("what's the weather") and played > 2.0,
                    {"user": user["content"], "played_s": round(played, 1), "closed_while_listening": closed_while_listening,
                     "opened_with_answer": opened_with_answer})

            # 13. Dictation (the mic): what's said goes into the message box, utterance after
            #     utterance across a pause, until the mic is pressed again; nothing is sent.
            first = (await piper.synthesize("Remind me to buy milk.")).samples
            second = (await piper.synthesize("And eggs for the weekend.")).samples
            np.concatenate([np.zeros(8000, np.float32), first, np.zeros(16000 * 3, np.float32), second,
                            np.zeros(16000 * 60, np.float32)]).astype(np.float32).tofile(os.environ["MEI_VOICE_SOURCE_FILE"])
            cfg = await h.runtime("GetConfig", {})
            config = {**cfg["config"], "voice": {**cfg["config"]["voice"], "end_pause_ms": 800}}  # reloads the file too
            await h.runtime("UpdateConfig", {"revision": cfg["revision"], "config": config})
            await asyncio.sleep(3.0)  # the worker reloads (and reads the new file)
            await h.until(lambda s: s["controller"]["voice"]["state"] == "idle", 60, "voice to reload")
            await h.hook("Popup", "new")
            sent_before = len((await h.state())["controller"]["messages"])
            named = ("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev", "ClickNamed", "s")
            [dictating] = await h._call(*named, ["Dictate"])
            box = lambda s: " ".join(s["shown"])  # noqa: E731  (the message box is among what the popup shows)
            st = await h.until(lambda s: "eggs" in box(s).lower(), 40, "both utterances in the box")
            await asyncio.sleep(3.0)  # a pause after: still dictating
            st = await h.state()
            still = st["controller"]["voice"]["state"] == "listening"
            text = box(st)
            await h.hook("PressEnter")  # Enter with the mic on: the mic stops, the words stay to edit
            st = await h.until(lambda s: s["controller"]["voice"]["state"] == "idle", 20, "Enter to stop dictation")
            await asyncio.sleep(3.0)  # nothing more arrives, and nothing went to Mei
            st = await h.state()
            kept = st["input"]
            h.check("dictation_goes_on_until_enter_and_sends_nothing", dictating and still and "milk" in text.lower()
                    and "eggs" in text.lower() and "eggs" in kept.lower()
                    and len(st["controller"]["messages"]) == sent_before,
                    {"box": text, "still_listening_after_a_pause": still, "kept": kept,
                     "sent": len(st["controller"]["messages"]) - sent_before})
            await h.use_fake([{"text": "Added to your list."}])
            await h.hook("PressEnter")  # a second Enter sends what's in the box, once
            st = await h.until(lambda s: len(s["controller"]["messages"]) >= sent_before + 2, 30, "the dictated message sent")
            await asyncio.sleep(3.0)  # and the words don't come back into the box
            st = await h.state()
            mine = [m["content"] for m in st["controller"]["messages"] if m["role"] == "user"]
            h.check("the_second_enter_sends_once_and_the_box_stays_empty",
                    len(mine) == 1 and "eggs" in mine[0].lower() and st["input"] == "",
                    {"sent": mine, "box_after": st["input"]})

            # 14. The box keeps its size: text in it, voice on and off again, several times (it used to
            #     shrink to nearly nothing until clicked).
            await h.hook("Popup", "new")
            await h.hook("Popup", "open")
            await asyncio.sleep(1.0)
            await h._call("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev", "TypeText", "s",
                          ["Hey, what's up? I want to search for some products on Amazon and also some products on Flipkart"])
            await asyncio.sleep(1.0)
            sizes = []
            for _ in range(5):
                await h._call(*named, ["Talk with Mei"])
                await h.until(lambda s: s["controller"]["voice"]["state"] == "listening", 20, "a conversation to start")
                await asyncio.sleep(0.8)
                await h._call(*named, ["Stop talking with Mei"])
                await h.until(lambda s: s["controller"]["voice"]["state"] == "idle", 20, "the conversation to end")
                for wait in (0.1, 0.5, 1.0):
                    await asyncio.sleep(wait)
                    sizes.append((await h.state())["inputSizes"])
            await h.hook("Screenshot", os.path.join(OUT, "input-after-voice.png"))
            h.check("the_box_keeps_its_size_after_voice", all(abs(z["scroll"] - z["needed"]) <= 2 for z in sizes[2::3])
                    and sizes[-1]["needed"] > 30, {"sizes": sizes})
    except AssertionError as e:
        h.results["error"] = str(e)
    finally:
        h.stop_shell()
        server.shutdown()
        # This session's runtime only, by its PID on this private bus: never by name, which would
        # also match the person's own runtime ("… -m mei serve").
        try:
            os.kill((await h.runtime("Hello", {"client": {"kind": "e2e"}, "protocol": [2, 1]}))["pid"], signal.SIGTERM)
        except (RuntimeError, ProcessLookupError, KeyError):
            pass  # not running
    print(json.dumps(h.results, indent=1))
    return 0 if h.results and all(v.get("ok") for k, v in h.results.items() if k != "error") \
        and "error" not in h.results else 1


sys.exit(asyncio.run(main()))
