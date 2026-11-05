"""Acting on an element (§10.2, decision 0022), in this order of preference:
an AT-SPI action, EditableText, focus and typed keys, a pointer click at the element's bounds.

Every injected key or pointer event first checks the control token, so a revoke stops a long string
halfway. AT-SPI actions and EditableText inject nothing (they ask the app itself), but they change
the app all the same: they check it too, just before the call.
"""

import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib  # noqa: E402

from mei.computer import geometry  # noqa: E402
from mei.computer.geometry import Rect, Stream, Window  # noqa: E402

from .control import Control  # noqa: E402
from .portal import PortalError, Session  # noqa: E402
from .tree import Node, Snapshot, TreeError, focused_role  # noqa: E402

SCREEN = 0  # the window id a whole-screen snapshot goes by (no window has it)
PREFERRED_ACTIONS = ("click", "press", "activate", "toggle", "jump", "select", "open")
KEY_GAP_S = 0.008
MODIFIERS = {"ctrl": 0xFFE3, "control": 0xFFE3, "shift": 0xFFE1, "alt": 0xFFE9, "super": 0xFFEB}
KEYS = {"return": 0xFF0D, "enter": 0xFF0D, "tab": 0xFF09, "escape": 0xFF1B, "esc": 0xFF1B, "backspace": 0xFF08,
        "delete": 0xFFFF, "home": 0xFF50, "end": 0xFF57, "left": 0xFF51, "up": 0xFF52, "right": 0xFF53,
        "down": 0xFF54, "page_up": 0xFF55, "pageup": 0xFF55, "page_down": 0xFF56, "pagedown": 0xFF56,
        "space": 0x20, "insert": 0xFF63, **{f"f{n}": 0xFFBE + n - 1 for n in range(1, 13)}}
TYPED = {"\n": 0xFF0D, "\t": 0xFF09}


class ActError(Exception):
    def __init__(self, error: str, message: str) -> None:
        super().__init__(message)
        self.error = error
        self.message = message


def keysym(char: str) -> int:
    if char in TYPED:
        return TYPED[char]
    code = ord(char)
    return code if 0x20 <= code <= 0x7E or 0xA0 <= code <= 0xFF else 0x01000000 | code


def combo(text: str) -> list[int]:
    """"ctrl+shift+t" → keysyms, modifiers first."""
    parts = [p.strip() for p in text.split("+") if p.strip()]
    if not parts:
        raise ActError("invalid", "no key given")
    *mods, key = parts
    out = []
    for m in mods:
        if m.lower() not in MODIFIERS:
            raise ActError("invalid", f"unknown modifier {m!r}")
        out.append(MODIFIERS[m.lower()])
    if key.lower() in KEYS:
        out.append(KEYS[key.lower()])
    elif len(key) == 1:
        out.append(keysym(key.lower() if mods else key))
    else:
        raise ActError("invalid", f"unknown key {key!r}")
    return out


class Hands:
    """Pointer and keyboard through the session, only while control holds."""

    def __init__(self, session: Session, control: Control) -> None:
        self._session = session
        self._control = control

    def check(self) -> None:
        """Control still holds (raises ControlLost if not): before an effect that injects nothing."""
        self._control.check()

    def streams(self, monitors: list) -> list[Stream]:
        """The session's streams, each with its frame width from its monitor's scale."""
        scales = {}
        for m in monitors:
            try:
                rect = Rect.parse(m)
                scales[(round(rect.x), round(rect.y))] = float(m.get("scale") or 1.0)
            except (ValueError, TypeError, AttributeError):
                continue
        return [Stream(s.node, s.rect, round(s.rect.width * scales.get((round(s.rect.x), round(s.rect.y)), 1.0)))
                for s in self._session.streams]

    def click(self, x: float, y: float, monitors: list, button: str = "left") -> None:
        self._point(x, y, monitors)
        for pressed in (True, False):
            self._control.check()
            self._session.button(button, pressed)

    def scroll(self, x: float, y: float, monitors: list, steps: int) -> None:
        self._point(x, y, monitors)
        self._control.check()
        self._session.scroll(steps)

    def type(self, text: str) -> None:
        for char in text:
            self._tap([keysym(char)])

    def key(self, text: str) -> None:
        self._tap(combo(text))

    def _point(self, x: float, y: float, monitors: list) -> None:
        stream = geometry.stream_at(self.streams(monitors), x, y)
        if stream is None:
            raise ActError("unavailable", "that point isn't on a screen Mei was allowed to use")
        for kind, a, b in geometry.pointer_moves(stream, x, y):
            self._control.check()
            if kind == "absolute":
                self._session.move_absolute(stream.node, a, b)
            else:
                self._session.move_relative(a, b)
        time.sleep(0.03)  # let the app see the pointer arrive before the press

    def _tap(self, keys: list[int]) -> None:
        for k in keys:
            self._control.check()
            self._session.keysym(k, True)
        for k in reversed(keys):
            self._session.keysym(k, False)  # releases always go out: no key is left held down
        time.sleep(KEY_GAP_S)


def act(snapshot: Snapshot, node: Node | None, action: str, text: str, point: list, window: Window,
        monitors: list, hands: Hands) -> str:
    """Do it; returns how ("action", "text", "keys", "pointer", "focus")."""
    if node is not None and node.password and action in ("set_text", "type"):
        raise ActError("handoff", "this is a password field: Mei never types into one")
    if node is None:
        if action in ("click", "scroll"):
            x, y = _picture_point(snapshot, point)
            if action == "click":
                hands.click(x, y, monitors)
            else:
                hands.scroll(x, y, monitors, _steps(text))
            return "pointer"
        if action in ("type", "key"):  # at whatever has the focus
            if action == "type":
                _typing_goes_somewhere_safe(window)
                hands.type(text)
            else:
                _not_into_a_password(window)
                hands.key(text)
            return "keys"
        raise ActError("invalid", f"{action} needs an element")
    if not node.enabled:
        raise ActError("invalid", f"{node.id} is disabled")
    if action in ("press", "toggle"):
        name = next((a for a in PREFERRED_ACTIONS if a in node.actions), node.actions[0] if node.actions else "")
        if name and _native(hands, lambda: Atspi.Action.do_action(node.accessible, _action_index(node, name))):
            return "action"
        hands.click(*geometry.element_point(window, node.extents), monitors)
        return "pointer"
    if action == "set_text":
        if node.editable and _native(hands, lambda: Atspi.EditableText.set_text_contents(node.accessible, text)):
            return "text"
        _focus(node, window, monitors, hands)
        _typing_goes_somewhere_safe(window)  # where the focus went, not where it was meant to
        hands.key("ctrl+a")
        hands.type(text)
        return "keys"
    if action == "type":
        _focus(node, window, monitors, hands)
        _typing_goes_somewhere_safe(window)
        hands.type(text)
        return "keys"
    if action == "key":
        _focus(node, window, monitors, hands)
        _not_into_a_password(window)
        hands.key(text)
        return "keys"
    if action == "focus":
        _focus(node, window, monitors, hands)
        return "focus"
    if action == "click":
        hands.click(*geometry.element_point(window, node.extents), monitors)
        return "pointer"
    if action == "scroll":
        hands.scroll(*geometry.element_point(window, node.extents), monitors, _steps(text))
        return "pointer"
    raise ActError("invalid", f"unknown action {action!r}")


def _action_index(node: Node, name: str) -> int:
    """The action's index among all of the element's actions (the snapshot lists only some)."""
    count = Atspi.Action.get_n_actions(node.accessible)
    return next(i for i in range(count) if Atspi.Action.get_action_name(node.accessible, i) == name)


def _steps(text: str) -> int:
    try:
        steps = int(text or "3")
    except ValueError:
        raise ActError("invalid", "scroll takes a number of steps (negative: up)") from None
    return max(-20, min(20, steps))


def _focus(node: Node, window: Window, monitors: list, hands: Hands) -> None:
    if "focused" in node.states:
        return
    if not _native(hands, lambda: Atspi.Component.grab_focus(node.accessible)):
        hands.click(*geometry.element_point(window, node.extents), monitors)
    time.sleep(0.05)


def _picture_point(snapshot: Snapshot, point: list) -> tuple[float, float]:
    if snapshot.picture is None:
        raise ActError("invalid", "this snapshot has no picture: name an element, or observe with a picture")
    if len(point) != 2 or not all(isinstance(v, (int, float)) for v in point):
        raise ActError("invalid", "a point is [x, y] in the picture")
    try:
        return snapshot.picture.logical(float(point[0]), float(point[1]))
    except ValueError as e:
        raise ActError("invalid", str(e)) from None


def _focused(window: Window) -> str | None:
    return None if window.id == SCREEN else focused_role(window)


def _typing_goes_somewhere_safe(window: Window) -> None:
    """Text is typed only where Mei can see what has the focus, and never into a password field
    (F07): the focus is looked up now, after any window was raised or element focused."""
    role = _focused(window)
    if role == "password text":
        raise ActError("handoff", "a password field has the focus: Mei never types into one")
    if role is None:
        raise ActError("handoff", "Mei can't tell what has the keyboard focus here")


def _not_into_a_password(window: Window) -> None:
    """A key (Return, a shortcut) may go where the focus can't be told, but not into a password field."""
    if _focused(window) == "password text":
        raise ActError("handoff", "a password field has the focus: Mei never types into one")


def _native(hands: Hands, call) -> bool:
    """An AT-SPI call that changes the app, only while control holds (checked at the last moment)."""
    hands.check()
    return _call(call)


def _call(call) -> bool:
    try:
        return bool(call())
    except GLib.Error:
        return False


__all__ = ["ActError", "Hands", "PortalError", "TreeError", "act", "combo", "keysym"]
