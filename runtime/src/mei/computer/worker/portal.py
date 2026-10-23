"""The RemoteDesktop session (decision 0022): pointer, keyboard, and the screens' pictures, through
xdg-desktop-portal. One consent in setup (persist_mode 2); its restore token starts every later session
with no dialog. Each start returns a new token, which the core stores."""

import itertools
import secrets

from gi.repository import Gio, GLib

from mei.computer.geometry import Rect, Stream

PORTAL = ("org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop")
REMOTE = "org.freedesktop.portal.RemoteDesktop"
CAST = "org.freedesktop.portal.ScreenCast"
KEYBOARD, POINTER = 1, 2
MONITOR = 1
PERSIST_UNTIL_REVOKED = 2
ASK_TIMEOUT_S = 180  # the first start waits on the person choosing in the dialog
QUICK_TIMEOUT_S = 15
BUTTONS = {"left": 272, "right": 273, "middle": 274}  # evdev BTN_*


class PortalError(Exception):
    def __init__(self, error: str, message: str) -> None:
        super().__init__(message)
        self.error = error
        self.message = message


class Session:
    def __init__(self, bus: Gio.DBusConnection) -> None:
        self._bus = bus
        self._sender = bus.get_unique_name().lstrip(":").replace(".", "_")
        self._tokens = itertools.count(1)
        self.handle: str | None = None
        self.streams: list[Stream] = []

    def open(self, restore_token: str) -> str:
        """Start a session; returns the new restore token ("" if the portal gave none)."""
        self.close()
        code, res = self._request(REMOTE, "CreateSession", "", (),
                                  {"session_handle_token": GLib.Variant("s", f"mei{secrets.token_hex(4)}")})
        if code != 0:
            raise PortalError("unavailable", "the remote desktop portal refused to start a session")
        handle = res["session_handle"]
        devices = {"types": GLib.Variant("u", KEYBOARD | POINTER), "persist_mode": GLib.Variant("u", PERSIST_UNTIL_REVOKED)}
        if restore_token:
            devices["restore_token"] = GLib.Variant("s", restore_token)
        self._expect(self._request(REMOTE, "SelectDevices", "o", (handle,), devices), "choosing the input devices")
        self._expect(self._request(CAST, "SelectSources", "o", (handle,),
                                   {"types": GLib.Variant("u", MONITOR), "multiple": GLib.Variant("b", True)}),
                     "choosing the screens")
        code, res = self._request(REMOTE, "Start", "os", (handle, ""), {},
                                  timeout_s=QUICK_TIMEOUT_S if restore_token else ASK_TIMEOUT_S)
        if code == 1:
            raise PortalError("permission", "the person didn't allow Mei to use the computer")
        if code != 0:
            raise PortalError("unavailable", "the remote desktop session didn't start")
        if not int(res.get("devices", 0)) & POINTER:
            self._close(handle)
            raise PortalError("permission", "the session was shared without remote interaction")
        self.handle = handle
        self.streams = [Stream(int(node), Rect(*props.get("position", (0, 0)), *props.get("size", (0, 0))), 0)
                        for node, props in res.get("streams", [])]
        return str(res.get("restore_token", ""))

    def close(self) -> None:
        handle, self.handle, self.streams = self.handle, None, []
        if handle:
            self._close(handle)

    def _close(self, handle: str) -> None:
        try:
            self._bus.call_sync(PORTAL[0], handle, "org.freedesktop.portal.Session", "Close", None, None,
                                Gio.DBusCallFlags.NONE, 3000, None)
        except GLib.Error:
            pass  # already gone

    # ── Input ────────────────────────────────────────────────────────────────

    def move_absolute(self, node: int, x: float, y: float) -> None:
        self._notify("NotifyPointerMotionAbsolute", "udd", (node, x, y))

    def move_relative(self, dx: float, dy: float) -> None:
        self._notify("NotifyPointerMotion", "dd", (dx, dy))

    def button(self, button: str, pressed: bool) -> None:
        self._notify("NotifyPointerButton", "iu", (BUTTONS[button], 1 if pressed else 0))

    def scroll(self, steps: int) -> None:
        self._notify("NotifyPointerAxisDiscrete", "ui", (0, steps))  # 0: vertical; positive is down

    def keysym(self, keysym: int, pressed: bool) -> None:
        self._notify("NotifyKeyboardKeysym", "iu", (keysym, 1 if pressed else 0))

    def pipewire_fd(self) -> int:
        """A PipeWire connection that sees only this session's streams."""
        handle = self._handle()
        reply, fds = self._bus.call_with_unix_fd_list_sync(PORTAL[0], PORTAL[1], CAST, "OpenPipeWireRemote",
                                                           GLib.Variant("(oa{sv})", (handle, {})),
                                                           GLib.VariantType("(h)"), Gio.DBusCallFlags.NONE, 5000,
                                                           None, None)
        return fds.get(reply.unpack()[0])

    def _notify(self, method: str, sig: str, args: tuple) -> None:
        try:
            self._bus.call_sync(PORTAL[0], PORTAL[1], REMOTE, method, GLib.Variant(f"(oa{{sv}}{sig})", (self._handle(), {}, *args)),
                                None, Gio.DBusCallFlags.NONE, 3000, None)
        except GLib.Error as e:
            raise PortalError("failed", f"the portal refused the input: {e.message}") from None

    def _handle(self) -> str:
        if self.handle is None:
            raise PortalError("unavailable", "no remote desktop session is open")
        return self.handle

    # ── Requests ─────────────────────────────────────────────────────────────

    def _request(self, iface: str, method: str, sig: str, args: tuple, options: dict,
                 timeout_s: float = QUICK_TIMEOUT_S) -> tuple[int, dict]:
        """Call a method that answers through a Request object, and wait for its Response."""
        token = f"mei{next(self._tokens)}{secrets.token_hex(3)}"
        path = f"/org/freedesktop/portal/desktop/request/{self._sender}/{token}"
        loop, got = GLib.MainLoop(), {}

        def on_response(_c, _s, _p, _i, _sig, params, _u) -> None:
            got["code"], got["results"] = params.unpack()
            loop.quit()

        sub = self._bus.signal_subscribe(PORTAL[0], "org.freedesktop.portal.Request", "Response", path, None,
                                         Gio.DBusSignalFlags.NONE, on_response, None)
        timer = GLib.timeout_add(int(timeout_s * 1000), loop.quit)
        try:
            opts = dict(options, handle_token=GLib.Variant("s", token))
            self._bus.call_sync(PORTAL[0], PORTAL[1], iface, method, GLib.Variant(f"({sig}a{{sv}})", (*args, opts)),
                                None, Gio.DBusCallFlags.NONE, 10000, None)
            loop.run()
        except GLib.Error as e:
            raise PortalError("unavailable", f"the portal failed: {e.message}") from None
        finally:
            self._bus.signal_unsubscribe(sub)
            if "code" in got:
                GLib.source_remove(timer)
        if "code" not in got:
            raise PortalError("timeout", "the portal didn't answer in time")
        return got["code"], got["results"]

    @staticmethod
    def _expect(answer: tuple[int, dict], what: str) -> None:
        if answer[0] != 0:
            raise PortalError("unavailable", f"the portal refused {what}")
