"""Spike 0b, portals from a host process (GNOME 50, xdg-desktop-portal 1.21): a non-interactive
Screenshot; ScreenCast + RemoteDesktop with persist_mode 2 and its restore token, what dialog the
first start shows and whether the token skips it the next time (also after a Shell restart); and
how RemoteDesktop's absolute pointer coordinates map to the screen (a real click on Calculator)."""

import sys
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gio, GLib  # noqa: E402

from shell import Shell, activate, app_named, find, press, save, text_of, walk

PORTAL = ("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
CONSENT = ("Share", "Allow", "Share Screen", "Remote Control", "Continue", "OK")
ANSWERED: list = []  # how each dialog's controls were worked: an AT-SPI action, or a click


class Portal:
    def __init__(self, shell: Shell) -> None:
        self.shell = shell
        self.bus = shell.bus
        self.sender = self.bus.get_unique_name().lstrip(":").replace(".", "_")
        self.n = 0
        self.dialogs: list[list[str]] = []

    def request(self, iface: str, method: str, sig: str, args: tuple, options: dict, timeout: float = 40.0):
        """Call a portal method that answers with a Request.Response; click through a consent dialog if
        one appears (and note what it said). Returns (response code, results, seconds, dialog seen)."""
        self.n += 1
        token = f"mei0b{self.n}"
        path = f"/org/freedesktop/portal/desktop/request/{self.sender}/{token}"
        got: dict = {}
        loop = GLib.MainLoop()

        def on_response(_c, _s, _p, _i, _sig, params, _u):
            got["code"], got["results"] = params.unpack()
            loop.quit()
        sub = self.bus.signal_subscribe(PORTAL[0], "org.freedesktop.portal.Request", "Response", path, None,
                                        Gio.DBusSignalFlags.NONE, on_response, None)
        opts = {k: v for k, v in options.items()}
        opts["handle_token"] = GLib.Variant("s", token)
        t0 = time.monotonic()
        self.bus.call_sync(PORTAL[0], PORTAL[1], iface, method, GLib.Variant(f"({sig}a{{sv}})", (*args, opts)), None,
                           Gio.DBusCallFlags.NONE, 30000, None)
        seen: list[str] = []

        def poll():
            texts = self.shell.stage_text()
            for label in CONSENT:  # a dialog drawn by the Shell
                if label in texts and self.shell.click_button(label):
                    seen.extend(["shell:", *texts])
                    self.shell.screenshot(f"dialog-{token}")
                    return False
            dialog = portal_dialog()  # a GTK window of the portal backend's
            if dialog is not None:
                seen.extend(["portal window:", *[f"{n.get_role_name()}:{n.get_name()}" for n in walk(dialog, 300)
                                                 if (n.get_name() or "").strip()][:60]])
                self.shell.screenshot(f"dialog-{token}")
                answer(dialog, self.shell)
                time.sleep(2)
                self.shell.screenshot(f"answered-{token}")
                return False
            return time.monotonic() - t0 < timeout
        GLib.timeout_add(700, poll)
        GLib.timeout_add(4000, lambda: (self.shell.screenshot(f"waiting-{token}"), False)[1])
        GLib.timeout_add(int(timeout * 1000), loop.quit)
        loop.run()
        self.bus.signal_unsubscribe(sub)
        if seen:
            self.dialogs.append(seen)
        return got.get("code", -1), got.get("results", {}), round(time.monotonic() - t0, 2), bool(seen)

    def call(self, iface: str, method: str, sig: str, args: tuple):
        return self.bus.call_sync(PORTAL[0], PORTAL[1], iface, method, GLib.Variant(f"({sig})", args), None,
                                  Gio.DBusCallFlags.NONE, 10000, None)


def portal_dialog():
    """The portal backend's consent window, if one is showing: found by what it says."""
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app is None:
            continue
        for n in walk(app, 300):
            try:
                if (n.get_name() or "") in ("Allow Remote Interaction", "Remote Desktop", "Screen Share"):
                    return app
            except GLib.Error:
                continue
    return None


def answer(dialog, shell: Shell) -> None:
    """What the person does once in setup: pick the first screen, allow interaction, Share."""
    nodes = walk(dialog, 400)
    how = []
    for n in nodes:  # every screen tile (toggle buttons named after each monitor): all screens shared
        if n.get_role_name() == "toggle button":
            how.append((f"screen {n.get_name()}", activate(n, shell)))
    for n in nodes:
        if (n.get_name() or "") == "Allow Remote Interaction" and n.get_role_name() == "switch":
            how.append(("interaction", activate(n, shell)))
            break
    time.sleep(0.8)
    share = find(dialog, "button", "Share")
    if share is not None:
        how.append(("share", activate(share, shell)))
    ANSWERED.append(how)


def remote_session(portal: Portal, restore: str | None) -> dict:
    rd, sc = "org.freedesktop.portal.RemoteDesktop", "org.freedesktop.portal.ScreenCast"
    code, res, took, _ = portal.request(rd, "CreateSession", "", (), {"session_handle_token": GLib.Variant("s", f"s{portal.n}")})
    out = {"create": code}
    if code != 0:
        return out
    session = res["session_handle"]
    devices = {"types": GLib.Variant("u", 3), "persist_mode": GLib.Variant("u", 2)}
    if restore:
        devices["restore_token"] = GLib.Variant("s", restore)
    out["select_devices"] = portal.request(rd, "SelectDevices", "o", (session,), devices)[0]
    out["select_sources"] = portal.request(sc, "SelectSources", "o", (session,),
                                           {"types": GLib.Variant("u", 1), "multiple": GLib.Variant("b", True)})[0]
    code, res, took, dialog = portal.request(rd, "Start", "os", (session, ""), {})
    out.update(start=code, start_s=took, dialog=dialog, devices=res.get("devices"),
               restore_token=bool(res.get("restore_token")), streams=[(s[0], s[1]) for s in res.get("streams", [])])
    out["session"] = session
    out["_token"] = res.get("restore_token", "")
    return out


def click_through_portal(portal: Portal, shell: Shell, session: str, streams, app) -> dict:
    """Click Calculator's 7 with RemoteDesktop's absolute motion, in the stream's coordinates."""
    seven = find(app, "button", "7")
    ext = Atspi.Component.get_extents(seven, Atspi.CoordType.WINDOW)
    buffer = shell.state()["window"]["buffer"]
    lx, ly = buffer["x"] + ext.x + ext.width / 2, buffer["y"] + ext.y + ext.height / 2
    tries = []
    for node, props in streams:
        pos, size = props.get("position", (0, 0)), props.get("size", (0, 0))
        if not (pos[0] <= lx < pos[0] + size[0] and pos[1] <= ly < pos[1] + size[1]):
            continue
        before = display(app)
        rd = "org.freedesktop.portal.RemoteDesktop"
        portal.call(rd, "NotifyPointerMotionAbsolute", "oa{sv}udd", (session, {}, node, lx - pos[0], ly - pos[1]))
        time.sleep(0.2)
        portal.call(rd, "NotifyPointerButton", "oa{sv}iu", (session, {}, 272, 1))
        portal.call(rd, "NotifyPointerButton", "oa{sv}iu", (session, {}, 272, 0))
        time.sleep(0.6)
        after = display(app)
        tries.append({"stream": node, "position": pos, "size": size, "logical": [round(lx), round(ly)],
                      "hit": "7" in after and after != before})
    return {"tries": tries}


def display(app) -> str:
    return " | ".join(t for t in (text_of(n) for n in walk(app, 400) if n.get_role_name() in ("text", "label", "editbar"))
                      if t.strip())[:120]


def activation_env(shell: Shell) -> None:
    """What a real session does at login: services the bus starts (the portals' dialogs) learn the display."""
    env = {"WAYLAND_DISPLAY": shell.wayland_display(), "XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "GNOME"}
    shell.call("UpdateActivationEnvironment", "a{ss}", env,
               iface=("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus"))
    # Portal backends already running on this private bus started without it: stop exactly those (by
    # the PID owning each name on this bus, never by name: the real session has its own), so the bus
    # starts them again with the display.
    import os
    import signal
    dbus = ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus")
    for name in ("org.freedesktop.portal.Desktop", "org.freedesktop.impl.portal.desktop.gnome",
                 "org.freedesktop.impl.portal.desktop.gtk"):
        try:
            pid = shell.call("GetConnectionUnixProcessID", "s", name, iface=dbus)[0]
        except GLib.Error:
            continue
        os.kill(pid, signal.SIGTERM)
    time.sleep(1)


def main() -> None:
    out = sys.argv[1]
    shell = Shell(out)
    shell.start()
    shell.enable_accessibility()
    Atspi.init()
    activation_env(shell)
    portal = Portal(shell)
    results: dict = {}
    try:
        shell.launch(["gnome-calculator"])  # a focused app, as there always is in a real session
        app = app_named("calculator", timeout=30)
        time.sleep(1.5)
        code, res, took, dialog = portal.request("org.freedesktop.portal.Screenshot", "Screenshot", "s", ("",),
                                                 {"interactive": GLib.Variant("b", False)})
        results["screenshot"] = {"code": code, "uri": bool(res.get("uri")), "s": took, "dialog": dialog}
        code, res, took, dialog = portal.request("org.freedesktop.portal.Screenshot", "Screenshot", "s", ("",),
                                                 {"interactive": GLib.Variant("b", False)})
        results["screenshot_again"] = {"code": code, "uri": bool(res.get("uri")), "s": took, "dialog": dialog}

        first = remote_session(portal, None)
        token = first.pop("_token")
        if first.get("start") == 0 and app is not None:
            first["click"] = click_through_portal(portal, shell, first["session"], [(n, p) for n, p in first["streams"]], app)
        results["remote_first"] = first
        portal.bus.call_sync(PORTAL[0], first.get("session", "/"), "org.freedesktop.portal.Session", "Close", None, None,
                             Gio.DBusCallFlags.NONE, 5000, None) if first.get("session") else None
        time.sleep(1)
        second = remote_session(portal, token)
        second.pop("_token")
        results["remote_with_token"] = second

        # Does the token outlive the Shell (and its portal backend)?
        for app in shell.apps:
            app.terminate()
        shell.apps.clear()
        shell.stop()
        time.sleep(2)
        shell.start()
        activation_env(shell)
        time.sleep(2)
        portal = Portal(shell)
        third = remote_session(portal, token)
        third.pop("_token")
        results["remote_after_shell_restart"] = third
        results["dialog_texts"] = portal.dialogs
        results["answered"] = ANSWERED
    except GLib.Error as e:
        results["error"] = e.message
    finally:
        save(out, "portals", results)
        print({k: v for k, v in results.items() if k != "dialog_texts"}, flush=True)
        shell.stop()


if __name__ == "__main__":
    main()
