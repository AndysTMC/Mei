"""Snapshots of a window's accessible tree (§10.1).

A snapshot keeps the interactive and text-bearing nodes that are showing, each under a short id (`e12`),
and is named by a random token. Acting names an element by token and id, so an id from an older snapshot
is refused (`stale`) instead of landing on whatever now sits there. Only a window's latest snapshot is
current: acting takes a new one, so ids from before the act are stale too.
"""

import secrets
import time
from dataclasses import dataclass, field

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib  # noqa: E402

from mei.computer.geometry import Picture, Rect, Window  # noqa: E402

INTERACTIVE = frozenset({
    "button", "toggle button", "check box", "radio button", "switch", "combo box", "entry", "text", "password text",
    "spin button", "slider", "menu item", "check menu item", "radio menu item", "link", "page tab", "list item",
    "tree item", "table cell", "menu", "scroll bar", "editbar", "push button",
})
TEXTUAL = frozenset({"label", "heading", "paragraph", "static", "caption", "status bar", "alert", "notification",
                     "tooltip", "title bar"})
SHOWN_STATES = {
    Atspi.StateType.FOCUSED: "focused", Atspi.StateType.CHECKED: "checked", Atspi.StateType.SELECTED: "selected",
    Atspi.StateType.EXPANDED: "expanded", Atspi.StateType.PRESSED: "pressed", Atspi.StateType.INDETERMINATE: "mixed",
}
MAX_VISITED = 6000  # nodes walked; a huge list stops here and the snapshot says it was cut
MAX_TEXT = 200


class TreeError(Exception):
    def __init__(self, error: str, message: str) -> None:
        super().__init__(message)
        self.error = error
        self.message = message


@dataclass
class Node:
    id: str
    role: str
    name: str
    text: str  # its value: a field's text, a slider's number
    states: tuple[str, ...]
    actions: tuple[str, ...]
    editable: bool
    extents: Rect  # WINDOW extents
    accessible: Atspi.Accessible = field(repr=False)
    enabled: bool = True

    @property
    def password(self) -> bool:
        return self.role == "password text"

    def view(self) -> dict:
        return {"id": self.id, "role": self.role, "name": self.name, "text": self.text, "states": list(self.states),
                "actions": list(self.actions), "editable": self.editable, "enabled": self.enabled,
                "bounds": [round(self.extents.x), round(self.extents.y), round(self.extents.width),
                           round(self.extents.height)]}


@dataclass
class Snapshot:
    token: str
    window: Window
    app: str
    nodes: dict[str, Node]
    truncated: bool
    picture: Picture | None = None
    taken: float = field(default_factory=time.monotonic)


EMBEDDED = "\ufffc"
# Chromium and Electron build what's inside a window only once a client asks one of its objects for its
# attributes, as screen readers do; until then the window shows its frame and next to nothing. So each look
# asks, and a window's first look gives its tree these moments to fill in, while it still grows.
FILLING_IN_S = (0.15, 0.35)


class Snapshots:
    """Each window's latest snapshot."""

    def __init__(self) -> None:
        self._by_window: dict[int, Snapshot] = {}

    def take(self, window: Window, max_nodes: int) -> Snapshot:
        frame, app = find_frame(window)
        _safe(frame.get_attributes)
        nodes, truncated = walk(frame, max_nodes)
        for wait in () if window.id in self._by_window else FILLING_IN_S:
            time.sleep(wait)
            before, (nodes, truncated) = len(nodes), walk(frame, max_nodes)
            if len(nodes) <= before:
                break
        snapshot = Snapshot(secrets.token_hex(6), window, app, nodes, truncated)
        self._by_window[window.id] = snapshot
        return snapshot

    def screen(self, window: Window) -> Snapshot:
        """The whole screen: no elements of its own (each window has those), only its picture."""
        snapshot = Snapshot(secrets.token_hex(6), window, "", {}, False)
        self._by_window[window.id] = snapshot
        return snapshot

    def node(self, token: str, element: str) -> tuple[Snapshot, Node]:
        snapshot = self.get(token)
        node = snapshot.nodes.get(element)
        if node is None:
            raise TreeError("not_found", f"no element {element} in that snapshot")
        return snapshot, node

    def get(self, token: str) -> Snapshot:
        snapshot = next((s for s in self._by_window.values() if s.token == token), None)
        if snapshot is None:
            raise TreeError("stale", "that snapshot is no longer current: observe again and use the new ids")
        return snapshot


def find_frame(window: Window) -> tuple[Atspi.Accessible, str]:
    """The accessible frame of a Shell window: its app is the one with the window's process, and among
    that app's frames the one with its title (or the active one)."""
    desktop = Atspi.get_desktop(0)
    candidates = []
    for i in range(desktop.get_child_count()):
        app = _safe(lambda i=i: desktop.get_child_at_index(i))
        if app is None or (window.pid and _safe(app.get_process_id) != window.pid):
            continue
        for j in range(_safe(app.get_child_count) or 0):
            frame = _safe(lambda j=j: app.get_child_at_index(j))
            if frame is not None:
                candidates.append((app, frame))
    if not candidates:
        raise TreeError("unavailable", "this window's app shows nothing to accessibility tools "
                                       "(it may need accessibility turned on, or have none)")
    titled = [(a, f) for a, f in candidates if (_safe(f.get_name) or "") == window.title]
    active = [(a, f) for a, f in candidates if _has(f, Atspi.StateType.ACTIVE)]
    app, frame = (titled or active or candidates)[0]
    return frame, _safe(app.get_name) or ""


def focused_role(window: Window) -> str | None:
    """The role of what has the keyboard focus in `window`, looked up now ("password text" for a
    password field); None when it can't be told: no accessible frame, or nothing in it focused."""
    try:
        frame, _app = find_frame(window)
    except TreeError:
        return None
    stack, visited = [frame], 0
    while stack and visited < MAX_VISITED:
        acc = stack.pop()
        visited += 1
        states = _safe(acc.get_state_set)
        if states is None:
            continue
        if states.contains(Atspi.StateType.FOCUSED):
            return _safe(acc.get_role_name) or ""
        if acc is not frame and not states.contains(Atspi.StateType.SHOWING):
            continue
        count = _safe(acc.get_child_count) or 0
        stack.extend(c for c in (_safe(lambda i=i: acc.get_child_at_index(i)) for i in range(min(count, 500)))
                     if c is not None)
    return None


def walk(root: Atspi.Accessible, max_nodes: int) -> tuple[dict[str, Node], bool]:
    """The showing nodes worth a model's attention, in reading order, up to `max_nodes`. A label inside
    a control that already says the same (a button's own text) is left out."""
    kept: dict[str, Node] = {}
    stack: list[tuple[Atspi.Accessible, str]] = [(root, "")]
    visited, truncated = 0, False
    while stack:
        acc, said = stack.pop()
        visited += 1
        if visited > MAX_VISITED or len(kept) >= max_nodes:
            truncated = True
            break
        states = _safe(acc.get_state_set)
        if states is None or (acc is not root and not states.contains(Atspi.StateType.SHOWING)):
            continue
        node = _node(acc, states, f"e{len(kept) + 1}")
        if node is not None and not (node.role in TEXTUAL and said and (node.text or node.name) == said):
            kept[node.id] = node
            said = node.name if node.role not in TEXTUAL else said
        count = _safe(acc.get_child_count) or 0
        children = [_safe(lambda i=i: acc.get_child_at_index(i)) for i in range(min(count, 500))]
        stack.extend((c, said) for c in reversed(children) if c is not None)
        truncated = truncated or count > 500
    return kept, truncated


def _node(acc: Atspi.Accessible, states, node_id: str) -> Node | None:
    role = _safe(acc.get_role_name) or ""
    interfaces = set(_safe(acc.get_interfaces) or ())
    name = (_safe(acc.get_name) or "").strip()
    actions = _actions(acc) if "Action" in interfaces else ()
    editable = "EditableText" in interfaces and states.contains(Atspi.StateType.EDITABLE)
    text = _text(acc, interfaces)
    interactive = role in INTERACTIVE or bool(actions) or editable
    if not interactive and not (role in TEXTUAL and (name or text)):
        return None
    extents = _safe(lambda: Atspi.Component.get_extents(acc, Atspi.CoordType.WINDOW)) if "Component" in interfaces else None
    if extents is None or extents.width <= 0 or extents.height <= 0:
        return None  # nowhere on screen: nothing to point at, nothing the person sees
    shown = tuple(label for state, label in SHOWN_STATES.items() if states.contains(state))
    enabled = states.contains(Atspi.StateType.ENABLED) or states.contains(Atspi.StateType.SENSITIVE) or not interactive
    return Node(node_id, role, name[:MAX_TEXT], text, shown, actions, editable,
                Rect(extents.x, extents.y, extents.width, extents.height), acc, enabled)


def _actions(acc: Atspi.Accessible) -> tuple[str, ...]:
    """What the element does when used. GTK's own actions on text ("clipboard.copy", "menu.popup") are
    left out: every selectable label has them, and they would make it look like a control."""
    count = _safe(lambda: Atspi.Action.get_n_actions(acc)) or 0
    names = (_safe(lambda i=i: Atspi.Action.get_action_name(acc, i)) for i in range(min(count, 12)))
    return tuple(n for n in names if n and "." not in n)


def _text(acc: Atspi.Accessible, interfaces: set[str]) -> str:
    if (_safe(acc.get_role_name) or "") == "password text":
        return ""  # never read back what someone typed into a password field
    if "Value" in interfaces:
        value = _safe(lambda: Atspi.Value.get_current_value(acc))
        if value is not None:
            return f"{value:g}"
    if "Text" in interfaces:
        count = _safe(lambda: Atspi.Text.get_character_count(acc)) or 0
        text = _safe(lambda: Atspi.Text.get_text(acc, 0, min(count, MAX_TEXT))) or ""
        # U+FFFC stands in a web page's (or any hypertext's) text for each child object: never words.
        return " ".join(text.replace(EMBEDDED, " ").split())[:MAX_TEXT]
    return ""


def _has(acc: Atspi.Accessible, state: Atspi.StateType) -> bool:
    states = _safe(acc.get_state_set)
    return bool(states and states.contains(state))


def _safe(call):
    """An AT-SPI call to another app, which may have gone or may not answer: None then."""
    try:
        return call()
    except GLib.Error:
        return None
