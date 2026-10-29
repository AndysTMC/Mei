"""The desktop worker's main loop: commands on stdin, events on stdout (wire.py).

A reader thread takes the lines. The control token's renewals and revokes are applied right there, so
they never wait behind a slow app. Everything else runs on the GLib main loop, one command at a time.
"""

import os
import sys
import threading
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gio, GLib  # noqa: E402

from mei.computer import geometry, wire  # noqa: E402
from mei.computer.geometry import Window  # noqa: E402

from . import frames  # noqa: E402
from .act import ActError, Hands, act  # noqa: E402
from .control import Control, ControlLost  # noqa: E402
from .portal import PortalError, Session  # noqa: E402
from .tree import Snapshot, Snapshots, TreeError  # noqa: E402

ATSPI_TIMEOUT_MS = 2000  # an app that doesn't answer AT-SPI in 2 s is treated as unreachable
SETTLE_S = 0.35  # after acting, before looking again: let the app redraw
MAX_PICTURE_WIDTH = 1280
MAX_SCREEN_WIDTH = 1600  # the whole screen, all monitors side by side: a little wider, as it shows more
SCREEN = 0  # the window id a whole-screen snapshot goes by (no window has it)
MAX_CHANGES = 20


class Output:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def send(self, message) -> None:
        data = wire.encode(message)
        with self._lock:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()


class Worker:
    def __init__(self, out: Output, bus: Gio.DBusConnection) -> None:
        self.out = out
        self.control = Control(self._on_revoked)
        self.session = Session(bus)
        self.hands = Hands(self.session, self.control)
        self.snapshots = Snapshots()
        self.handlers = {wire.Observe: self.observe, wire.Act: self.act, wire.OpenSession: self.open_session,
                         wire.CloseSession: self.close_session}

    def handle(self, cmd) -> bool:
        try:
            data = self.handlers[type(cmd)](cmd)
            reply = wire.Reply(id=cmd.id, ok=True, data=data)
        except (TreeError, ActError, PortalError) as e:
            reply = wire.Reply(id=cmd.id, ok=False, error=e.error, message=e.message)
        except ControlLost as e:
            reply = wire.Reply(id=cmd.id, ok=False, error="revoked", message=f"stopped: {e}")
        except frames.FrameError as e:
            reply = wire.Reply(id=cmd.id, ok=False, error="unavailable", message=str(e))
        except Exception as e:  # noqa: BLE001  a bug: say so, keep serving
            print(f"{type(cmd).__name__} failed: {e!r}", file=sys.stderr, flush=True)
            reply = wire.Reply(id=cmd.id, ok=False, error="failed", message="it failed inside the desktop worker")
        self.out.send(reply)
        return False  # a GLib idle callback: once

    # ── Commands ─────────────────────────────────────────────────────────────

    def observe(self, cmd: wire.Observe) -> dict:
        if cmd.screen:
            return self._screen(cmd.monitors)
        window = _window(cmd.window)
        snapshot = self.snapshots.take(window, max(10, min(cmd.max_nodes, 600)))
        data = _view(snapshot)
        if cmd.image:
            data["picture"] = self._picture(snapshot, cmd.monitors)
        return data

    def act(self, cmd: wire.Act) -> dict:
        if cmd.element:
            snapshot, node = self.snapshots.node(cmd.token, cmd.element)
        else:
            snapshot, node = self.snapshots.get(cmd.token), None
        window = _window(cmd.window) if cmd.window else snapshot.window
        how = act(snapshot, node, cmd.action, cmd.text, cmd.point, window, cmd.monitors, self.hands)
        time.sleep(SETTLE_S)
        if window.id == SCREEN:  # no tree to look at again: a new look at the screen shows what changed
            return {"how": how, "changes": [], "token": ""}
        try:
            after = self.snapshots.take(window, max(len(snapshot.nodes) + 50, 100))
        except TreeError:
            return {"how": how, "changes": ["the window closed or stopped answering"], "token": ""}
        return {"how": how, "changes": changes(snapshot, after), **_view(after)}

    def open_session(self, cmd: wire.OpenSession) -> dict:
        token = self.session.open(cmd.restore_token)
        return {"restore_token": token,
                "streams": [{"node": s.node, "x": s.rect.x, "y": s.rect.y, "width": s.rect.width,
                             "height": s.rect.height} for s in self.session.streams]}

    def close_session(self, _cmd: wire.CloseSession) -> dict:
        self.session.close()
        return {}

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _screen(self, monitors: list) -> dict:
        """The whole screen: every monitor, in one picture (decision 0036)."""
        streams = self.hands.streams(monitors)
        if not streams:
            raise PortalError("unavailable", "no picture: computer use's screen session isn't open")
        grabbed = []
        for stream in streams:
            frame = frames.grab(self.session.pipewire_fd(), stream.node)
            grabbed.append((geometry.Stream(stream.node, stream.rect, frame.get_width()), frame))
        picture, places = geometry.screen_picture([s for s, _f in grabbed], MAX_SCREEN_WIDTH)
        bounds = geometry.Rect(picture.x, picture.y, picture.width * picture.per_pixel, picture.height * picture.per_pixel)
        snapshot = self.snapshots.screen(Window(id=SCREEN, title="the screen", pid=0, buffer=bounds))
        snapshot.picture = picture
        frame_of = {s.node: f for s, f in grabbed}
        png = frames.screen_png([(frame_of[s.node], place) for s, place in places], picture.width, picture.height)
        return {**_view(snapshot), "picture": {"png": png, "width": picture.width, "height": picture.height}}

    def _picture(self, snapshot: Snapshot, monitors: list) -> dict:
        streams = self.hands.streams(monitors)
        window = snapshot.window
        stream = geometry.stream_at(streams, *window.buffer.center) or next(
            (s for s in streams if window.buffer.intersection(s.rect)), None)
        if stream is None:
            raise PortalError("unavailable", "no picture: the window isn't on a screen Mei was allowed to see"
                              if streams else "no picture: computer use's screen session isn't open")
        frame = frames.grab(self.session.pipewire_fd(), stream.node)
        stream = geometry.Stream(stream.node, stream.rect, frame.get_width())
        cut = geometry.window_picture(window, stream, MAX_PICTURE_WIDTH)
        if cut is None:
            raise PortalError("unavailable", "no picture: the window isn't on that screen")
        crop, picture = cut
        snapshot.picture = picture
        return {"png": frames.png(frame, crop, picture.width, picture.height), "width": picture.width,
                "height": picture.height}

    def _on_revoked(self, reason: str, by: str) -> None:  # any thread
        self.out.send(wire.Revoked(reason=reason, by=by))
        GLib.idle_add(lambda: (self.session.close(), False)[1])


def _window(value: dict) -> Window:
    try:
        return Window.parse(value)
    except (ValueError, TypeError) as e:
        raise TreeError("invalid", f"bad window: {e}") from None


def _view(snapshot: Snapshot) -> dict:
    return {"token": snapshot.token, "app": snapshot.app, "title": snapshot.window.title,
            "nodes": [n.view() for n in snapshot.nodes.values()], "truncated": snapshot.truncated}


def changes(before: Snapshot, after: Snapshot) -> list[str]:
    """What changed between two snapshots of a window, in words: the act's evidence (§10.2)."""
    def keyed(snapshot: Snapshot) -> dict:
        seen: dict[tuple, int] = {}
        out = {}
        for n in snapshot.nodes.values():
            key = (n.role, n.name)
            seen[key] = seen.get(key, 0) + 1
            out[(*key, seen[key])] = n
        return out

    old, new = keyed(before), keyed(after)
    lines = []
    for key, n in new.items():
        was = old.get(key)
        label = f"{n.role} “{n.name}”" if n.name else n.role
        if was is None:
            lines.append(f"+ {n.id} {label}" + (f": “{n.text}”" if n.text else ""))
        elif was.text != n.text:
            lines.append(f"{n.id} {label}: now “{n.text}”")
        elif set(was.states) != set(n.states):
            gained, lost = set(n.states) - set(was.states), set(was.states) - set(n.states)
            lines.append(f"{n.id} {label}: " + ", ".join([*(f"now {s}" for s in sorted(gained)),
                                                          *(f"no longer {s}" for s in sorted(lost))]))
    gone = [k for k in old if k not in new]
    lines += [f"- {k[0]} “{k[1]}”" if k[1] else f"- {k[0]}" for k in gone]
    if len(lines) > MAX_CHANGES:
        lines = [*lines[:MAX_CHANGES], f"… and {len(lines) - MAX_CHANGES} more"]
    return lines or ["nothing visible changed"]


def read_commands(worker: Worker, loop: GLib.MainLoop) -> None:
    for line in sys.stdin.buffer:
        try:
            cmd = wire.command(line)
        except wire.WireError as e:
            print(f"ignored a bad command: {e}", file=sys.stderr, flush=True)
            continue
        if isinstance(cmd, wire.Lease):
            worker.control.lease(cmd.generation, cmd.valid_ms)
        elif isinstance(cmd, wire.Revoke):
            worker.control.revoke(cmd.reason or "the core revoked control")
            GLib.idle_add(lambda: (worker.session.close(), False)[1])
        elif isinstance(cmd, wire.Quit):
            break
        else:
            GLib.idle_add(worker.handle, cmd)
    worker.control.revoke("the core went away")
    GLib.idle_add(lambda: (worker.session.close(), loop.quit(), False)[2])


def main() -> None:
    Atspi.init()
    Atspi.set_timeout(ATSPI_TIMEOUT_MS, 5 * ATSPI_TIMEOUT_MS)
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    out = Output()
    worker = Worker(out, bus)
    worker.control.watch_shell(os.environ["DBUS_SESSION_BUS_ADDRESS"])
    loop = GLib.MainLoop()
    threading.Thread(target=read_commands, args=(worker, loop), name="commands", daemon=True).start()
    try:
        reachable = Atspi.get_desktop(0).get_child_count() >= 0
    except GLib.Error:
        reachable = False
    out.send(wire.Ready(version=wire.VERSION, accessibility=reachable))
    loop.run()


if __name__ == "__main__":
    main()
