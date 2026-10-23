"""The control token (§10.3): the worker injects input only while all of these hold.

- **A lease from the core** that hasn't run out: renewed every 250 ms, valid for 600 ms. If the core
  freezes or dies, input stops on its own.
- **The Shell is present.** The unique name that owned `org.gnome.Shell` when control began still owns it.
- **Nothing revoked control.** The Shell's kill switch broadcasts `ControlRevoked`, the core sends `Revoke`.

The Shell is watched on a thread of its own, with its own bus connection and main context, so a revoke
lands within milliseconds even while the main thread waits on a slow app.
"""

import sys
import threading
import time
from collections.abc import Callable

from gi.repository import Gio, GLib

SHELL = "org.gnome.Shell"
CONTROL_PATH = "/com/andystmc/Mei1/Control"
CONTROL_IFACE = "com.andystmc.Mei1.Control"
TICK_S = 0.05


class ControlLost(Exception):
    pass


class Control:
    def __init__(self, revoked: Callable[[str, str], None]) -> None:
        """`revoked(reason, by)` is called once each time input stops (any thread); `by` is shell, lease or core."""
        self._revoked = revoked
        self._lock = threading.Lock()
        self._generation = -1
        self._expires = 0.0
        self._why_not = "no task holds the computer"
        self._shell_owner: str | None = None

    # ── From the core (the reader thread) ────────────────────────────────────

    def lease(self, generation: int, valid_ms: int) -> None:
        """Renew control; `valid_ms` 0 ends it in good order (the act is done), which isn't a revoke."""
        with self._lock:
            if generation < self._generation:
                return  # an old renewal arriving late
            if generation > self._generation:
                self._why_not = ""  # a new period of control
            self._generation = generation
            if valid_ms <= 0:
                self._expires, self._why_not = 0.0, "no task holds the computer"
                return
            self._expires = time.monotonic() + valid_ms / 1000

    def revoke(self, reason: str, by: str = "core") -> None:
        with self._lock:
            ongoing = self._generation >= 0 and not self._why_not
            self._expires = 0.0
            self._why_not = reason or "control was revoked"
        if ongoing:
            self._revoked(self._why_not, by)

    # ── Before every injected event (the main thread) ────────────────────────

    def check(self) -> None:
        with self._lock:
            if not self._active():
                raise ControlLost(self._why_not or "the core stopped renewing control")

    def _active(self) -> bool:
        return not self._why_not and time.monotonic() < self._expires and self._shell_owner is not None

    # ── The Shell, on its own thread ─────────────────────────────────────────

    def watch_shell(self, address: str) -> None:
        threading.Thread(target=self._watch, args=(address,), name="shell-watch", daemon=True).start()

    def _watch(self, address: str) -> None:
        context = GLib.MainContext.new()
        context.push_thread_default()
        try:
            bus = Gio.DBusConnection.new_for_address_sync(
                address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
                None, None)
            owner = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                  "GetNameOwner", GLib.Variant("(s)", (SHELL,)), GLib.VariantType("(s)"),
                                  Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]
        except GLib.Error as e:  # no Shell to watch: input stays off
            print(f"can't watch the Shell: {e.message}", file=sys.stderr, flush=True)
            return
        with self._lock:
            self._shell_owner = owner

        def owner_changed(_c, _s, _p, _i, _sig, params, _u) -> None:
            name, _old, new = params.unpack()
            if name == SHELL and new != owner:
                with self._lock:
                    self._shell_owner = None
                self.revoke("the Shell went away", "shell")

        def control_revoked(_c, sender, _p, _i, _sig, params, _u) -> None:
            if sender == owner:  # only the Shell that was there when control began
                self.revoke(params.unpack()[0] if params.n_children() else "stopped from the Shell", "shell")

        def tick() -> bool:
            with self._lock:
                ran_out = self._generation >= 0 and not self._why_not and time.monotonic() >= self._expires
            if ran_out:
                self.revoke("the core stopped renewing control", "lease")
            return True

        bus.signal_subscribe("org.freedesktop.DBus", "org.freedesktop.DBus", "NameOwnerChanged", "/org/freedesktop/DBus",
                             SHELL, Gio.DBusSignalFlags.NONE, owner_changed, None)
        bus.signal_subscribe(SHELL, CONTROL_IFACE, "ControlRevoked", CONTROL_PATH, None, Gio.DBusSignalFlags.NONE,
                             control_revoked, None)
        timer = GLib.timeout_source_new(int(TICK_S * 1000))
        timer.set_callback(lambda *_: tick())
        timer.attach(context)
        while True:
            context.iteration(True)
