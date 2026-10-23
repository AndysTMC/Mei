"""End-to-end for computer use: Stage 6's acceptance (architecture §22, decision 0022).

Everything is private, set up by scripts/e2e-computer.sh:
- a headless GNOME Shell with two virtual monitors, its runtime dir, session bus and keyring;
- its own PipeWire with no devices (for the screen's stream), and no camera, microphone or speaker of the
  person's within reach;
- the dev-built extension and the D-Bus-activated runtime, driven by the scripted model;
- two test apps: a GTK4 form, and a canvas whose square only a picture shows.

Checks, against what the apps themselves received and what AT-SPI reads back:
1. A form is filled and submitted through AT-SPI only, before the screen is allowed: no pointer, no keys.
   (Its check box has no AT-SPI action, as GTK4's switches haven't: it's toggled by pointer after setup.)
2. Its password field is handed to the person, and nothing is typed into it.
3. Setup's one consent (GNOME's dialog) keeps a restore token; later tasks show no dialog.
4. The canvas is clicked from a picture, at 100 % and at 150 %.
5. A pointer act waits while the person moves the mouse, then goes on by itself.
6. The kill switch stops typing within 200 ms with the runtime frozen (SIGSTOP).
7. Typing stops within 600 ms when the runtime is killed, and when Mei's extension goes away.

Runs on the system's Python (PyGObject: Atspi, Gio). Prints one JSON object; exits 1 if a check failed.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gio, GLib  # noqa: E402

OUT = Path(sys.argv[1])
APPS = Path(__file__).resolve().parent / "apps"
HOOKS = ("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev")
RUNTIME = ("com.andystmc.Mei1", "/com/andystmc/Mei1", "com.andystmc.Mei1.Runtime")
DBUS = ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus")
DISPLAY = ("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig", "org.gnome.Mutter.DisplayConfig")
EXTENSIONS = ("org.gnome.Shell.Extensions", "/org/gnome/Shell/Extensions", "org.gnome.Shell.Extensions")
UUID = "mei@andystmc.com"
FORM, CANVAS = "Mei test form", "Mei test canvas"
SQUARE = (220, 140, 60)  # as canvas.py draws it
LONG_TEXT = "the quick brown fox jumps over the lazy dog " * 8
WIREPLUMBER = """
wireplumber.profiles = {
  mei-e2e = {
    inherits = [ policy, mixin.stateless ]
    check.no-media-session = disabled
    support.snapd-permission-prompting = disabled
    support.reserve-device = disabled
    support.logind = disabled
  }
}
"""

BUS = Gio.bus_get_sync(Gio.BusType.SESSION)
RESULTS: dict = {}
PROCS: list[subprocess.Popen] = []
DIALOGS_AFTER_SETUP: list[str] = []


# ── The session ──────────────────────────────────────────────────────────────


def call(iface: tuple, member: str, sig: str = "", *args, timeout_ms: int = 10000):
    dest, path, interface = iface
    reply = BUS.call_sync(dest, path, interface, member, GLib.Variant(f"({sig})", args) if sig else None, None,
                          Gio.DBusCallFlags.NONE, timeout_ms, None)
    return reply.unpack() if reply is not None else None


def state() -> dict:
    return json.loads(call(HOOKS, "State")[0])


def runtime(member: str, args: dict | None = None, timeout_ms: int = 30000) -> dict:
    return json.loads(call(RUNTIME, member, "s", json.dumps(args or {}), timeout_ms=timeout_ms)[0])


def check(name: str, ok: bool, detail=None) -> None:
    RESULTS[name] = {"ok": bool(ok), **({"detail": detail} if detail is not None else {})}


def until(predicate, timeout: float, what: str, every: float = 0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except GLib.Error:
            pass  # not up yet
        pump(every)
    raise TimeoutError(f"timed out waiting for {what}")


def pump(seconds: float) -> None:
    """Sleep while letting GLib deliver what it has (async replies)."""
    deadline = time.monotonic() + seconds
    context = GLib.MainContext.default()
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        time.sleep(0.01)


def private_pipewire() -> None:
    """The private session's own PipeWire, for the screen's stream: WirePlumber's policy without any
    device monitor, on the private runtime dir. Refuses to go on if it somehow has a device."""
    runtime_dir = os.environ["XDG_RUNTIME_DIR"]
    if runtime_dir.startswith("/run/user/"):
        raise RuntimeError("not a private runtime dir")
    conf = Path(os.environ["XDG_CONFIG_HOME"], "wireplumber", "wireplumber.conf.d")
    conf.mkdir(parents=True, exist_ok=True)
    (conf / "e2e.conf").write_text(WIREPLUMBER)
    log = open(OUT / "pipewire.log", "a")
    PROCS.append(subprocess.Popen(["/usr/bin/pipewire"], stdout=log, stderr=log))
    until(lambda: Path(runtime_dir, "pipewire-0").exists(), 10, "PipeWire")
    PROCS.append(subprocess.Popen(["/usr/bin/wireplumber", "-p", "mei-e2e"], stdout=log, stderr=log))
    pump(1.0)
    dump = json.loads(subprocess.run(["/usr/bin/pw-dump"], capture_output=True, text=True, timeout=10).stdout or "[]")
    if any(o.get("type", "").endswith(":Device") for o in dump):
        raise RuntimeError("the private PipeWire has a device")


def start_shell() -> None:
    log = open(OUT / "shell.log", "a")
    PROCS.append(subprocess.Popen(["gnome-shell", "--headless", "--wayland", "--no-x11", "--virtual-monitor",
                                   "1280x800", "--virtual-monitor", "1280x800"], stdout=log, stderr=log))
    until(lambda: state()["controller"]["status"] == "connected", 90, "the extension to connect")
    until(lambda: not state()["startingUp"], 60, "the Shell to finish starting up")


def wayland_display() -> str:
    found = re.findall(r"Using Wayland display name '([^']+)'", (OUT / "shell.log").read_text())
    return found[-1]


def prepare_session() -> None:
    """What a real login does: the bus's services learn the display, and the accessibility bus is on."""
    env = {"WAYLAND_DISPLAY": wayland_display(), "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"}
    call(DBUS, "UpdateActivationEnvironment", "a{ss}", env)
    for name in ("org.freedesktop.portal.Desktop", "org.freedesktop.impl.portal.desktop.gnome",
                 "org.freedesktop.impl.portal.desktop.gtk"):  # started without it: by PID on this bus only
        try:
            os.kill(call(DBUS, "GetConnectionUnixProcessID", "s", name)[0], signal.SIGTERM)
        except GLib.Error:
            continue
    props = ("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties")
    call(props, "Set", "ssv", "org.a11y.Status", "IsEnabled", GLib.Variant("b", True))
    Atspi.init()
    pump(1.0)


def launch(script: str, output: Path) -> subprocess.Popen:
    env = {**os.environ, "WAYLAND_DISPLAY": wayland_display(), "GDK_BACKEND": "wayland"}
    env.pop("DISPLAY", None)
    log = open(OUT / f"app-{script}.log", "a")
    proc = subprocess.Popen(["/usr/bin/python3", str(APPS / f"{script}.py"), str(output)], env=env, stdout=log,
                            stderr=log)
    PROCS.append(proc)
    title = FORM if script == "form" else CANVAS
    until(lambda: call(HOOKS, "ActivateWindow", "s", title)[0] and (state()["window"] or {}).get("title") == title,
          20, f"{script} to show")  # a window opened without a click may not get the focus
    pump(0.5)
    return proc


def close(proc: subprocess.Popen) -> None:
    """End a test app and wait for its window to go: the next scenario may open one with the same title."""
    proc.terminate()
    proc.wait(10)
    pump(1.0)


def apply_scales(scale: float) -> None:
    serial, monitors, _logical, _props = call(DISPLAY, "GetCurrentState")
    layout, x = [], 0
    for spec, modes, _ in monitors:
        mode = next((m for m in modes if m[6].get("is-current")), modes[0])
        chosen = min(mode[5], key=lambda s: abs(s - scale))
        layout.append((x, 0, chosen, 0, x == 0, [(spec[0], mode[0], {})]))
        x += round(mode[1] / chosen)
    call(DISPLAY, "ApplyMonitorsConfig", "uua(iiduba(ssa{sv}))a{sv}", serial, 1, layout, {})
    pump(2.0)


# ── AT-SPI, from outside Mei (to answer GNOME's dialog, and to read what the apps show) ──


def apps(name: str):
    desktop = Atspi.get_desktop(0)
    return [a for a in (desktop.get_child_at_index(i) for i in range(desktop.get_child_count()))
            if a is not None and name.lower() in (a.get_name() or "").lower()]


def walk(root, limit: int = 3000):
    out, queue = [], [root]
    while queue and len(out) < limit:
        node = queue.pop(0)
        if node is None:
            continue
        out.append(node)
        try:
            queue.extend(node.get_child_at_index(i) for i in range(node.get_child_count()))
        except GLib.Error:
            pass
    return out


def node(title: str, role: str, name: str | None = None):
    """An element in the window with this title, found the way a screen reader would."""
    desktop = Atspi.get_desktop(0)
    for app in (desktop.get_child_at_index(i) for i in range(desktop.get_child_count())):
        for frame in (app.get_child_at_index(j) for j in range(app.get_child_count())) if app else ():
            if frame is None or frame.get_name() != title:
                continue
            for n in walk(frame):
                try:
                    if n.get_role_name() == role and (name is None or n.get_name() == name):
                        return n
                except GLib.Error:
                    continue
    return None


def canvas_area():
    """The canvas's drawing area: the largest leaf in its window (its role name varies by GTK version)."""
    frame = node(CANVAS, "frame") or node(CANVAS, "window")
    if frame is None:
        return None
    sized = [(e.width * e.height, n) for n in walk(frame)[1:] if n.get_child_count() == 0
             and (e := Atspi.Component.get_extents(n, Atspi.CoordType.WINDOW)).width > 0]
    return max(sized, key=lambda s: s[0])[1] if sized else None


def text_of(n) -> str:
    return Atspi.Text.get_text(n, 0, Atspi.Text.get_character_count(n))


def portal_dialog():
    for app in apps("portal"):
        for n in walk(app, 400):
            try:
                if n.get_name() == "Allow Remote Interaction":
                    return app
            except GLib.Error:
                continue
    return None


def click_node(n) -> None:
    """A person's click on it: its window's buffer origin plus its window extents (decision 0022)."""
    ext = Atspi.Component.get_extents(n, Atspi.CoordType.WINDOW)
    buffer = state()["window"]["buffer"]
    call(HOOKS, "Click", "ii", round(buffer["x"] + ext.x + ext.width / 2), round(buffer["y"] + ext.y + ext.height / 2))
    pump(0.6)


def answer_dialog(dialog) -> None:
    """What the person does once in setup: share every screen, allow interaction, Share."""
    nodes = walk(dialog, 400)
    for n in nodes:  # the screens' tiles: select each one not selected yet
        if n.get_role_name() == "toggle button" and not n.get_state_set().contains(Atspi.StateType.CHECKED):
            Atspi.Action.do_action(n, 0)
            pump(0.3)
    switch = next(n for n in nodes if n.get_name() == "Allow Remote Interaction" and n.get_role_name() == "switch")
    for _ in range(3):  # a GTK4 switch has no AT-SPI action: a click, checked until it took
        if switch.get_state_set().contains(Atspi.StateType.CHECKED):
            break
        click_node(switch)
    share = next(n for n in nodes if n.get_role_name() == "button" and n.get_name() == "Share")
    Atspi.Action.do_action(share, 0)


# ── Mei ──────────────────────────────────────────────────────────────────────


def use_script(script: list[dict], preset: str = "balanced") -> None:
    cfg = runtime("GetConfig")
    config = cfg["config"]
    config["providers"]["fake"] = {"options": {"script": script, "delay_ms": 0}}
    config.update(active="fake", approvals={**config.get("approvals", {}), "preset": preset},
                  computer={"enabled": True})
    runtime("UpdateConfig", {"revision": cfg["revision"], "config": config})
    until(lambda: state()["controller"]["provider"] == "fake", 10, "the popup to see the scripted model")


def send(text: str) -> str:
    """A message typed into the popup; returns its conversation."""
    call(HOOKS, "Popup", "s", "new")
    call(HOOKS, "Popup", "s", "open")
    call(HOOKS, "Send", "s", text)
    return until(lambda: state()["controller"]["current"], 10, "the message to be accepted")


def task(conversation: str) -> dict:
    tasks = runtime("GetConversation", {"conversation_id": conversation})["tasks"]
    return tasks[-1] if tasks else {}


def reaches(conversation: str, states: set[str], timeout: float = 30) -> dict:
    return until(lambda: (t := task(conversation)).get("state") in states and t, timeout, f"a task in {states}")


def press(label: str) -> None:
    """A button in the popup's input area (approvals and questions only take the Shell's own clicks)."""
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if call(HOOKS, "ClickButton", "s", label)[0]:
            pump(0.5)
            if state()["clicks"][-1]["clicked"]:
                return
        else:
            pump(0.3)
    raise TimeoutError(f"“{label}” never took a click")


def approve_until(conversation: str, states: set[str], timeout: float = 60) -> dict:
    """Allow each act that asks, until the task reaches one of `states`."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        t = reaches(conversation, {"WAITING_APPROVAL", *states}, deadline - time.monotonic())
        if t["state"] != "WAITING_APPROVAL":
            return t
        press("Allow once")
    raise TimeoutError(f"the task didn't reach {states}")


def approve_until_done(conversation: str, timeout: float = 60) -> dict:
    return approve_until(conversation, {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED"}, timeout)


def runtime_pid() -> int:
    return call(DBUS, "GetConnectionUnixProcessID", "s", RUNTIME[0])[0]


def watch_dialogs() -> None:
    if portal_dialog() is not None:
        DIALOGS_AFTER_SETUP.append(time.strftime("%H:%M:%S"))


# ── Scenarios ────────────────────────────────────────────────────────────────


def form_through_atspi() -> None:
    out = OUT / "form.json"
    form = launch("form", out)
    use_script([
        {"tool_calls": [{"name": "desktop_observe", "arguments": {"window": FORM}}]},
        {"tool_calls": [{"name": "desktop_act", "arguments": {"snapshot": "$snapshot", "action": "set_text",
                                                               "element": "$e:text:Name", "text": "Ada Lovelace"}}]},
        {"tool_calls": [{"name": "desktop_act", "arguments": {"snapshot": "$snapshot", "action": "set_text",
                                                               "element": "$e:text:Email", "text": "ada@example.org"}}]},
        {"tool_calls": [{"name": "desktop_act", "arguments": {"snapshot": "$snapshot", "action": "set_text",
                                                               "element": "$e:password text:Password",
                                                               "text": "hunter2"}}]},
        {"tool_calls": [{"name": "desktop_observe", "arguments": {"window": FORM}}]},
        {"tool_calls": [{"name": "desktop_act", "arguments": {"snapshot": "$snapshot", "action": "press",
                                                               "element": "$e:button:Submit"}}]},
        {"text": "Submitted the form."}])
    conversation = send(f"Fill in the {FORM} for Ada Lovelace, ada@example.org, and submit it")
    handed = approve_until(conversation, {"WAITING_INPUT", "FAILED", "BLOCKED", "COMPLETED"})
    asked = (handed.get("input_request") or {}).get("kind")
    call(HOOKS, "Screenshot", "s", str(OUT / "computer-handoff.png"))
    password = node(FORM, "password text", "Password")
    typed = text_of(password) if password is not None else "?"
    press("Done")
    done = approve_until_done(conversation)
    sent = json.loads(out.read_text()) if out.exists() else {}
    acts = [a for a in done.get("actions", []) if a.get("capability") == "desktop.act"]
    check("form_filled_and_submitted_through_atspi_only",
          done["state"] == "COMPLETED" and sent.get("name") == "Ada Lovelace" and sent.get("email") == "ada@example.org"
          and not runtime("ComputerStatus")["screen"]
          and all(a["execution"] == "SUCCEEDED" for a in acts),
          {"state": done["state"], "form": sent, "acts": [(a["description"], a["execution"]) for a in acts]})
    check("password_is_handed_to_the_person", asked == "handoff" and typed == "" and sent.get("password_filled") is False,
          {"asked": asked, "typed_into_it": len(typed)})
    close(form)


def checkbox_by_pointer() -> None:
    """A GTK4 check box has no AT-SPI action (like a switch): once the screen is allowed, the pointer toggles it."""
    form = launch("form", OUT / "form-checkbox.json")
    use_script([
        {"tool_calls": [{"name": "desktop_observe", "arguments": {"window": FORM}}]},
        {"tool_calls": [{"name": "desktop_act", "arguments": {"snapshot": "$snapshot", "action": "toggle",
                                                               "element": "$e:check box:Send me news"}}]},
        {"text": "Done."}])
    conversation = send(f"Tick “Send me news” in the {FORM}")
    done = approve_until_done(conversation)  # "Send me news": an outward word, so it asks
    box = node(FORM, "check box", "Send me news")
    checked = box is not None and box.get_state_set().contains(Atspi.StateType.CHECKED)
    check("checkbox_toggled_by_pointer_after_setup", done["state"] == "COMPLETED" and checked,
          {"state": done["state"], "checked": checked})
    close(form)


def setup_consent() -> None:
    reply: dict = {}

    def done(source, result) -> None:
        try:
            reply.update(json.loads(source.call_finish(result).unpack()[0]))
        except GLib.Error as e:
            reply["error"] = e.message

    BUS.call(RUNTIME[0], RUNTIME[1], RUNTIME[2], "ComputerAllowScreen", GLib.Variant("(s)", ("{}",)), None,
             Gio.DBusCallFlags.NONE, 240_000, None, done)
    dialog = until(portal_dialog, 30, "GNOME's screen dialog")
    call(HOOKS, "Screenshot", "s", str(OUT / "computer-consent.png"))
    answer_dialog(dialog)
    until(lambda: reply, 60, "the consent to finish")
    status = runtime("ComputerStatus")
    check("setup_allows_the_screen_once", reply.get("ok") is True and status["screen"], {"reply": reply, "status": status})


def canvas_from_a_picture(scale: float) -> None:
    out = OUT / f"canvas-{scale:g}.log"
    if scale != 1:
        apply_scales(scale)
    proc = launch("canvas", out)
    pump(1.0)
    window = state()["window"]
    area = until(canvas_area, 10, "the canvas's drawing area")
    ext = Atspi.Component.get_extents(area, Atspi.CoordType.WINDOW)
    buffer = window["buffer"]
    picture_width = min(1280, round(buffer["width"] * scale))
    per_pixel = buffer["width"] / picture_width
    x, y, size = SQUARE
    point = [round((ext.x + x + size / 2) / per_pixel), round((ext.y + y + size / 2) / per_pixel)]
    use_script([
        {"tool_calls": [{"name": "desktop_observe", "arguments": {"window": CANVAS, "picture": True}}]},
        {"tool_calls": [{"name": "desktop_act", "arguments": {"snapshot": "$snapshot", "action": "click",
                                                               "point": point}}]},
        {"text": "Clicked the square."}])
    conversation = send(f"Click the red square in the {CANVAS}")
    done = approve_until_done(conversation)
    clicks = out.read_text().split() if out.exists() else []
    check(f"canvas_clicked_from_a_picture_at_{round(scale * 100)}", done["state"] == "COMPLETED" and "hit" in clicks,
          {"state": done["state"], "point": point, "clicks": clicks})
    close(proc)


def pauses_for_the_person() -> None:
    out = OUT / "canvas-pause.log"
    proc = launch("canvas", out)
    pump(1.0)
    window = state()["window"]
    area = until(canvas_area, 10, "the canvas's drawing area")
    ext = Atspi.Component.get_extents(area, Atspi.CoordType.WINDOW)
    scale = next((m["scale"] for m in state()["monitors"]
                  if m["x"] <= window["buffer"]["x"] < m["x"] + m["width"]), 1.0)
    per_pixel = window["buffer"]["width"] / min(1280, round(window["buffer"]["width"] * scale))
    x, y, size = SQUARE
    point = [round((ext.x + x + size / 2) / per_pixel), round((ext.y + y + size / 2) / per_pixel)]
    use_script([
        {"tool_calls": [{"name": "desktop_observe", "arguments": {"window": CANVAS, "picture": True}}]},
        {"tool_calls": [{"name": "desktop_act", "arguments": {"snapshot": "$snapshot", "action": "click",
                                                               "point": point}}]},
        {"text": "Clicked."}])
    conversation = send(f"Click the red square in the {CANVAS}")
    reaches(conversation, {"WAITING_APPROVAL"})
    press("Allow once")
    seen, moved_until = set(), time.monotonic() + 4
    while time.monotonic() < moved_until:  # the person moves the mouse around for four seconds
        call(HOOKS, "Scroll", "iii", 900 + int(time.monotonic() * 37) % 200, 300, 0)
        seen.add(task(conversation).get("state"))
        pump(0.25)
    paused_clicks = out.read_text().split() if out.exists() else []
    done = reaches(conversation, {"COMPLETED", "FAILED", "BLOCKED", "CANCELLED"}, 30)
    clicks = out.read_text().split() if out.exists() else []
    check("pointer_act_waits_while_the_person_moves_the_mouse",
          "WAITING_RESOURCE" in seen and not paused_clicks and done["state"] == "COMPLETED" and "hit" in clicks,
          {"states_seen": sorted(s for s in seen if s), "clicks_while_moving": paused_clicks, "clicks": clicks})
    close(proc)


def typing(conversation_text: str):
    """Start typing a long text into the form's Name field; returns (conversation, the field)."""
    use_script([
        {"tool_calls": [{"name": "desktop_observe", "arguments": {"window": FORM}}]},
        {"tool_calls": [{"name": "desktop_act", "arguments": {"snapshot": "$snapshot", "action": "type",
                                                               "element": "$e:text:Email", "text": LONG_TEXT}}]},
        {"text": "Typed it."}])
    field = node(FORM, "text", "Email")
    Atspi.EditableText.set_text_contents(field, "")
    conversation = send(conversation_text)
    until(lambda: len(text_of(field)) > 20, 30, "typing to begin")
    return conversation, field


def stops_within(field, stop, limit_s: float) -> dict:
    """Do `stop`, then watch the field: how long after it did the text last grow?"""
    before = len(text_of(field))
    started = time.monotonic()
    stop()
    last_change, length = started, len(text_of(field))
    while time.monotonic() - started < 2.0:
        now = len(text_of(field))
        if now != length:
            last_change, length = time.monotonic(), now
        time.sleep(0.005)
    return {"stopped_after_ms": round((last_change - started) * 1000), "typed_before": before, "typed_after": length,
            "of": len(LONG_TEXT), "ok": length < len(LONG_TEXT) and last_change - started < limit_s}


def kill_switch_with_the_runtime_frozen() -> None:
    form = launch("form", OUT / "form-kill.json")
    conversation, field = typing(f"Type a long text into the Email field of the {FORM}")
    pid = runtime_pid()
    os.kill(pid, signal.SIGSTOP)
    try:
        measured = stops_within(field, lambda: call(HOOKS, "PressStopShortcut"), 0.2)
    finally:
        os.kill(pid, signal.SIGCONT)
    done = reaches(conversation, {"CANCELLED", "COMPLETED", "FAILED", "BLOCKED"}, 30)
    check("kill_switch_stops_input_within_200ms_with_the_runtime_frozen",
          measured["ok"] and done["state"] == "CANCELLED", {**measured, "task": done["state"]})
    close(form)


def runtime_killed() -> None:
    form = launch("form", OUT / "form-killed.json")
    _conversation, field = typing(f"Type a long text into the Email field of the {FORM}")
    measured = stops_within(field, lambda: os.kill(runtime_pid(), signal.SIGKILL), 0.6)
    check("input_stops_within_600ms_when_the_runtime_is_killed", measured["ok"], measured)
    close(form)
    until(lambda: state()["controller"]["status"] == "connected", 60, "the runtime to come back")


def extension_gone() -> None:
    form = launch("form", OUT / "form-gone.json")
    _conversation, field = typing(f"Type a long text into the Email field of the {FORM}")
    measured = stops_within(field, lambda: call(EXTENSIONS, "DisableExtension", "s", UUID), 0.6)
    check("input_stops_within_600ms_when_the_extension_goes_away", measured["ok"], measured)
    call(EXTENSIONS, "EnableExtension", "s", UUID)
    until(lambda: state()["controller"]["status"] == "connected", 60, "the extension to come back")
    close(form)


def main() -> int:
    try:
        private_pipewire()
        start_shell()
        prepare_session()
        runtime("SetupApply", {"step": "offered"})
        form_through_atspi()
        setup_consent()
        GLib.timeout_add(500, lambda: (watch_dialogs(), True)[1])
        checkbox_by_pointer()
        canvas_from_a_picture(1.0)
        pauses_for_the_person()
        kill_switch_with_the_runtime_frozen()
        runtime_killed()
        extension_gone()
        canvas_from_a_picture(1.5)
        check("no_portal_dialog_after_setup", not DIALOGS_AFTER_SETUP, DIALOGS_AFTER_SETUP)
    except Exception:  # noqa: BLE001  report what got done, and why it stopped
        import traceback
        RESULTS["error"] = traceback.format_exc()[-2000:]
        try:
            current = state()["controller"]["current"]
            t = task(current) if current else {}
            RESULTS["last_task"] = {"state": t.get("state"), "error": t.get("error"),
                                    "actions": [(a["capability"], a["execution"], a.get("error")) for a in t.get("actions", [])]}
            RESULTS["log"] = [f"{e.get('logger')}: {e.get('msg')}" for e in runtime("GetLogs", {"after": 0}).get("entries", [])][-40:]
        except (GLib.Error, KeyError, TypeError) as e:
            RESULTS["diagnostics"] = str(e)
        try:
            call(HOOKS, "Screenshot", "s", str(OUT / "computer-error.png"))
        except GLib.Error:
            pass
    finally:
        for proc in reversed(PROCS):
            proc.terminate()
        for proc in PROCS:
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()
    print(json.dumps(RESULTS, indent=1), flush=True)
    return 0 if RESULTS and "error" not in RESULTS and all(r["ok"] for r in RESULTS.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
