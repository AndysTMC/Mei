"""Spike 0b helpers: a private headless GNOME Shell with two virtual monitors, Mei's dev hooks
(screenshots, clicks by coordinates or by a button's label anywhere in the Shell), apps launched on
the nested display, and AT-SPI walking. Throwaway code; system Python with PyGObject."""

import atexit
import json
import os
import re
import subprocess
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gio, GLib  # noqa: E402

HOOKS = ("org.gnome.Shell", "/com/andystmc/MeiDev", "com.andystmc.MeiDev")

# WirePlumber's policy alone: links streams, but has no ALSA, Bluetooth, V4L2 or libcamera monitor,
# so this PipeWire has no devices at all. Portal access stays on (it asks this bus's portal).
WIREPLUMBER = """
wireplumber.profiles = {
  mei-0b = {
    inherits = [ policy, mixin.stateless ]
    check.no-media-session = disabled
    support.snapd-permission-prompting = disabled
    support.reserve-device = disabled
    support.logind = disabled
  }
}
"""
_pipewire: list[subprocess.Popen] = []


def private_pipewire(out: str) -> None:
    """A PipeWire of the private session's own (for screencasts), on its private runtime dir. The
    person's PipeWire is never reachable: run.sh links nothing of the real runtime dir in."""
    if _pipewire:
        return
    runtime = os.environ["XDG_RUNTIME_DIR"]
    if runtime.startswith("/run/user/") or any(k in os.environ for k in ("PIPEWIRE_REMOTE", "PIPEWIRE_RUNTIME_DIR")):
        raise RuntimeError("not a private runtime dir: refusing to start PipeWire")
    conf = os.path.join(os.environ["XDG_CONFIG_HOME"], "wireplumber", "wireplumber.conf.d")
    os.makedirs(conf, exist_ok=True)
    with open(os.path.join(conf, "0b.conf"), "w") as f:
        f.write(WIREPLUMBER)
    log = open(os.path.join(out, "pipewire.log"), "a")
    _pipewire.append(subprocess.Popen(["/usr/bin/pipewire"], stdout=log, stderr=log))
    for _ in range(50):
        if os.path.exists(os.path.join(runtime, "pipewire-0")):
            break
        time.sleep(0.1)
    _pipewire.append(subprocess.Popen(["/usr/bin/wireplumber", "-p", "mei-0b"], stdout=log, stderr=log))
    time.sleep(1)
    atexit.register(lambda: [p.terminate() for p in reversed(_pipewire)])
    # Refuse to go on if it somehow has a device (it must have none).
    dump = json.loads(subprocess.run(["/usr/bin/pw-dump"], capture_output=True, text=True, timeout=10).stdout or "[]")
    devices = [o for o in dump if o.get("type", "").endswith(":Device")
               or ((o.get("info") or {}).get("props") or {}).get("media.class", "").endswith(("/Source", "/Sink"))]
    if devices:
        raise RuntimeError(f"the private PipeWire has devices: {[d.get('id') for d in devices]}")


class Shell:
    def __init__(self, out: str, monitors=("1280x800", "1920x1080")) -> None:
        self.out = out
        self.monitors = monitors
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.proc: subprocess.Popen | None = None
        self.apps: list[subprocess.Popen] = []

    def start(self) -> None:
        private_pipewire(self.out)
        log = open(os.path.join(self.out, "shell.log"), "a")
        args = ["gnome-shell", "--headless", "--wayland", "--no-x11"]
        for m in self.monitors:
            args += ["--virtual-monitor", m]
        self.proc = subprocess.Popen(args, stdout=log, stderr=log)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if not self.state()["startingUp"]:
                    return
            except GLib.Error:
                pass
            time.sleep(0.25)
        raise RuntimeError("the Shell didn't start")

    def stop(self) -> None:
        for app in self.apps:
            app.terminate()
        for app in self.apps:
            try:
                app.wait(5)
            except subprocess.TimeoutExpired:
                app.kill()
        if self.proc:
            self.proc.terminate()
            self.proc.wait(20)

    def call(self, member: str, sig: str = "", *args, iface=HOOKS, timeout_ms=10000):
        dest, path, interface = iface
        params = GLib.Variant(f"({sig})", args) if sig else None
        reply = self.bus.call_sync(dest, path, interface, member, params, None, Gio.DBusCallFlags.NONE, timeout_ms, None)
        return reply.unpack() if reply is not None else None

    def state(self) -> dict:
        return json.loads(self.call("State")[0])

    def screenshot(self, name: str) -> str:
        path = os.path.join(self.out, f"{name}.png")
        self.call("Screenshot", "s", path)
        return path

    def click(self, x: float, y: float) -> None:
        self.call("Click", "ii", round(x), round(y))
        time.sleep(0.6)

    def click_button(self, label: str) -> bool:
        return bool(self.call("ClickStageButton", "s", label)[0])

    def stage_text(self) -> list[str]:
        return json.loads(self.call("StageText")[0])

    def wayland_display(self) -> str:
        log = open(os.path.join(self.out, "shell.log")).read()
        found = re.findall(r"Using Wayland display name '([^']+)'", log)
        if not found:
            raise RuntimeError("no Wayland display in the Shell's log")
        return found[-1]

    def launch(self, argv: list[str], **env) -> subprocess.Popen:
        full = {**os.environ, "WAYLAND_DISPLAY": self.wayland_display(), "XDG_SESSION_TYPE": "wayland",
                "GDK_BACKEND": "wayland", "NO_AT_BRIDGE": "0", **env}
        full.pop("DISPLAY", None)
        log = open(os.path.join(self.out, f"app-{os.path.basename(argv[0])}.log"), "a")
        proc = subprocess.Popen(argv, env=full, stdout=log, stderr=log, start_new_session=True)
        self.apps.append(proc)
        return proc

    def enable_accessibility(self) -> None:
        """What a screen reader does: tells toolkits (Chromium, Electron) to build their trees."""
        self.call("Set", "ssv", "org.a11y.Status", "IsEnabled", GLib.Variant("b", True),
                  iface=("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties"))
        self.call("Set", "ssv", "org.a11y.Status", "ScreenReaderEnabled", GLib.Variant("b", True),
                  iface=("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties"))


# ── AT-SPI ────────────────────────────────────────────────────────────────


def app_named(*names: str, timeout: float = 30.0):
    """The accessible application whose name contains one of `names` (case-insensitive)."""
    deadline = time.monotonic() + timeout
    wanted = [n.lower() for n in names]
    while time.monotonic() < deadline:
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            name = (app.get_name() or "").lower() if app else ""
            if app and any(w in name for w in wanted):
                return app
        time.sleep(0.25)
    return None


def walk(root, limit: int = 20000):
    """Every node under root, breadth first (bounded)."""
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


def describe(node) -> dict:
    d = {"role": node.get_role_name(), "name": node.get_name() or ""}
    try:
        action = node.get_action_iface()
        d["actions"] = [action.get_action_name(i) for i in range(action.get_n_actions())] if action else []
    except GLib.Error:
        d["actions"] = []
    d["editable"] = node.get_editable_text_iface() is not None
    d["text"] = node.get_text_iface() is not None
    comp = node.get_component_iface()
    if comp is not None:
        try:
            for name, kind in (("screen", Atspi.CoordType.SCREEN), ("window", Atspi.CoordType.WINDOW)):
                r = comp.get_extents(kind)
                d[name] = [r.x, r.y, r.width, r.height]
        except GLib.Error:
            pass
    states = node.get_state_set()
    d["showing"] = states.contains(Atspi.StateType.SHOWING)
    return d


def find(root, role: str, name: str | None = None, contains: bool = False, limit: int = 20000):
    for node in walk(root, limit):
        try:
            if node.get_role_name() != role:
                continue
            n = node.get_name() or ""
            if name is None or (name.lower() in n.lower() if contains else n == name):
                return node
        except GLib.Error:
            continue
    return None


def text_of(node) -> str:
    if node.get_text_iface() is None:
        return node.get_name() or ""
    return Atspi.Text.get_text(node, 0, Atspi.Text.get_character_count(node))


def press(node) -> bool:
    """Its first AT-SPI action, if it has one (a GTK4 switch has none)."""
    if node.get_action_iface() is None or Atspi.Action.get_n_actions(node) == 0:
        return False
    return Atspi.Action.do_action(node, 0)


def activate(node, shell: "Shell") -> str:
    """Its AT-SPI action, or else a click where it is (window extents + the window's buffer origin)."""
    if press(node):
        return "action"
    ext = Atspi.Component.get_extents(node, Atspi.CoordType.WINDOW)
    buffer = shell.state()["window"]["buffer"]
    shell.click(buffer["x"] + ext.x + ext.width / 2, buffer["y"] + ext.y + ext.height / 2)
    return "click"


def set_text(node, text: str) -> bool:
    return node.get_editable_text_iface() is not None and Atspi.EditableText.set_text_contents(node, text)


def save(out: str, name: str, data) -> None:
    with open(os.path.join(out, f"{name}.json"), "w") as f:
        json.dump(data, f, indent=1, default=str)
