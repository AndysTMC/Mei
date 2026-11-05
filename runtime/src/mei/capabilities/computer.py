"""Computer use (§10, decision 0022): look at a window, and act on what's in it.

`desktop.observe` gives the window's controls and text as elements (e1, e2, …) bound to a snapshot.
`desktop.act` names one by snapshot and id, so an id from an older snapshot is refused.

What an act may do is judged from the observed element, never from what the model says (§10.4). An
unfamiliar button can submit a payment without saying "pay", so an act's effect is `unknown` (policy asks
in every mode) unless the element shows it's low risk: typing into a plain text field, flipping a
checkbox or switch, focusing, scrolling, opening a menu or tab. Labels like send, buy or delete only make
it stricter. Mei never types into a password field: it hands that field to the person.
"""

import contextlib
import re
from typing import Annotated, Literal

import msgspec

from .base import (READ_ONLY, ActionContext, ActionResult, AVAILABLE, Availability, Capability, CapabilityError,
                   Effects, Env, Resource, Window)

Action = Literal["press", "toggle", "set_text", "type", "key", "focus", "click", "scroll"]
MAX_LINES = 400
SCREEN = {"id": 0, "title": "the screen"}  # what a whole-screen snapshot stands for (no window has id 0)
SPARSE = 2  # elements or fewer: the window's controls aren't visible to Mei, so it also takes a picture
LOW_RISK = Effects(mutates="local", undo="none")
UNKNOWN = Effects(mutates="unknown", undo="none")
TOGGLES = frozenset({"check box", "switch", "toggle button", "radio button", "check menu item", "radio menu item"})
OPENERS = frozenset({"menu", "combo box", "page tab", "tree item", "list item", "expander"})
TEXT_FIELDS = frozenset({"text", "entry", "spin button", "editbar"})
SAFE_KEYS = frozenset({"tab", "shift+tab", "escape", "esc", "up", "down", "left", "right", "home", "end",
                       "page_up", "page_down", "pageup", "pagedown", "backspace", "delete"})
# Labels that mean someone else will see it, or something leaves for good: stricter, never looser.
OUTWARD = re.compile(r"\b(send|submit|post|publish|share|reply|buy|order|pay|purchase|checkout|transfer|confirm|"
                     r"delete|remove|erase|discard|sign|accept|agree|subscribe|book)\b", re.IGNORECASE)
MESSAGING = re.compile(r"mail|geary|thunderbird|evolution|telegram|signal|slack|discord|element|fractal|teams|"
                       r"whatsapp|polari|chat", re.IGNORECASE)
HANDOFF = "Please fill in “{field}” in {app} yourself: Mei never types into password fields. Choose Done when it's filled in."
# When the worker finds, just before typing, that it can't tell where the keys would go (F07).
HANDOFF_UNSURE = ("Please type “{text}” in {app} yourself: Mei can't tell what would receive the keys there, and it "
                  "never types into password fields. Choose Done when it's typed.")
HANDOFF_DONE, HANDOFF_SKIP = "Done", "Skip it"


def _available(env: Env) -> Availability:
    if env.desktop is None:
        return Availability.unavailable("computer use isn't set up here")
    if env.bridge() is None:
        return Availability.unavailable("the Shell isn't connected")
    return AVAILABLE


async def _screen(env: Env) -> tuple[list[Window], list[dict]]:
    bridge = env.bridge()
    if bridge is None:
        raise CapabilityError("unavailable", "the Shell isn't connected")
    return await bridge.list_windows(), await bridge.monitors()


def window_dict(w: Window) -> dict:
    return {"id": w.id, "title": w.title, "pid": w.pid, "buffer": w.buffer, "focused": w.focused, "app_id": w.app_id}


def pick_window(windows: list[Window], wanted: str) -> Window:
    """The window the model means: an id from windows_list, an app's name or id, or "" for the focused one."""
    shown = [w for w in windows if w.buffer]
    if not wanted.strip():
        found = next((w for w in shown if w.focused), None)
        if found is None:
            raise CapabilityError("not_found", "no window has the focus; name one (windows_list gives ids)")
        return found
    key = wanted.strip().lower()
    by_id = [w for w in shown if str(w.id) == key]
    named = [w for w in shown if key in (w.app_id.lower(), w.app_id.lower().rsplit(".", 1)[-1], w.title.lower())]
    found = (by_id or named or [w for w in shown if key in w.title.lower()])
    if not found:
        raise CapabilityError("not_found", f"no window matches {wanted!r}; windows_list gives the open ones")
    return next((w for w in found if w.focused), found[0])


def outline(data: dict, cut: int = MAX_LINES) -> str:
    """A snapshot as the model reads it: one line per element."""
    head = f"Window “{data.get('title', '')}” ({data.get('app', '')}), snapshot {data.get('token', '')}. " \
           "Act with desktop_act on these ids; they expire when you observe again."
    lines = [head]
    for n in data.get("nodes", [])[:cut]:
        label = f" “{n['name']}”" if n.get("name") else ""
        value = f" = “{n['text']}”" if n.get("text") and n.get("text") != n.get("name") else ""
        flags = [*n.get("states", []), *([] if n.get("enabled", True) else ["disabled"])]
        if n.get("role") == "password text":
            flags.append("password: the person fills it in")
        lines.append(f"{n['id']} {n.get('role', '')}{label}{value}" + (f" [{', '.join(flags)}]" if flags else ""))
    if data.get("truncated"):
        lines.append("(more elements than shown: observe a smaller window, or scroll)")
    picture = data.get("picture")
    if isinstance(picture, dict):
        lines.append(f"Picture: {picture.get('width')}×{picture.get('height')} pixels, attached. For a place no element "
                     "covers, desktop_act with action click and point [x, y] in it.")
    return "\n".join(lines)


# ── desktop.observe ──────────────────────────────────────────────────────────


class ObserveParams(msgspec.Struct, kw_only=True):
    screen: Annotated[bool, msgspec.Meta(description="The whole screen instead of one window: a picture of everything "
                                                     "shown (every window, notifications, the top bar), and the open "
                                                     "windows listed")] = False
    window: Annotated[str, msgspec.Meta(description="Which window: its id from windows_list, or its app's name. "
                                                    "Empty: the window in front")] = ""
    picture: Annotated[bool, msgspec.Meta(description="Also a picture of it: only when its elements aren't enough "
                                                      "(a canvas, an image, a game)")] = False


class DesktopObserve(Capability):
    name = "desktop.observe"
    summary = ("Look at the screen: the whole of it as a picture (screen=true), or a window's controls and text as "
               "elements (e1, e2, …) to act on with desktop_act, optionally with a picture.")
    Params = ObserveParams
    idempotent = True
    timeout_s = 45.0

    def available(self, env: Env) -> Availability:
        return _available(env)

    def resources(self, p: ObserveParams, env: Env) -> list[Resource]:
        return [Resource(kind="screen", value="screen", access="read", role="screen", aliases=("screen",))]

    def describe(self, p: ObserveParams, env: Env) -> str:
        if p.screen:
            return "Look at the whole screen"
        what = p.window or "the window in front"
        return f"Look at {what}" + (" and take a picture of it" if p.picture else "")

    async def run(self, p: ObserveParams, ctx: ActionContext) -> ActionResult:
        desktop = ctx.env.desktop
        assert desktop is not None
        windows, monitors = await _screen(ctx.env)
        if p.screen:  # everything shown, as a picture, with the windows named (decision 0036)
            data = await _desktop(desktop.observe(SCREEN, monitors, picture=True, screen=True))
            listed = "\n".join(f"- {w.title} ({w.app_id or 'unknown app'}), id {w.id}" for w in windows if w.title)
            observation = (f"The whole screen, snapshot {data.get('token', '')}.\n"
                           + (f"Open windows (look at one with desktop_observe window=<id> for its controls):\n"
                              f"{listed}\n" if listed else "") + outline(data).split("\n", 1)[-1])
            return ActionResult(ok=True, observation=observation.rstrip(), summary="Looked at the whole screen",
                                data_class="screen", trust="untrusted", images=[data["picture"]["png"]])
        window = pick_window(windows, p.window)
        data = await _desktop(desktop.observe(window_dict(window), monitors, picture=p.picture))
        if not p.picture and len(data.get("nodes", [])) <= SPARSE:
            # Nothing to act on but the window itself (decision 0035): web pages in Chrome show no controls
            # to assistive tools, and the owner's tasks looped clicking by point on snapshots with no
            # picture. A picture is what there is to see, so it comes along.
            with contextlib.suppress(CapabilityError):  # no screen permission: the elements it has
                data = await _desktop(desktop.observe(window_dict(window), monitors, picture=True))
        images = [data["picture"]["png"]] if isinstance(data.get("picture"), dict) else []
        return ActionResult(ok=True, observation=outline(data), summary=f"Looked at {window.title or 'a window'}",
                            data_class="screen", trust="untrusted", images=images)


# ── desktop.act ──────────────────────────────────────────────────────────────


class ActParams(msgspec.Struct, kw_only=True):
    snapshot: Annotated[str, msgspec.Meta(description="The snapshot the element is from (desktop_observe gives it)")]
    action: Annotated[Action, msgspec.Meta(description=(
        "press: a button or menu item; toggle: a checkbox or switch; set_text: replace a field's text; type: type "
        "at the element; key: a key or shortcut like Return or ctrl+s; focus; click: at the element, or at `point` "
        "in the snapshot's picture; scroll: `text` steps, negative up"))]
    element: Annotated[str, msgspec.Meta(description="The element's id, e.g. e12")] = ""
    point: Annotated[list[float], msgspec.Meta(max_length=2, description="[x, y] in the snapshot's picture, "
                                                                         "for click without an element")] = \
        msgspec.field(default_factory=list)
    text: Annotated[str, msgspec.Meta(max_length=5000, description="For set_text, type, key and scroll")] = ""


class DesktopAct(Capability):
    name = "desktop.act"
    summary = ("Act on an element of a window you observed: press, toggle, set or type text, a key, focus, click, "
               "scroll. Names it by snapshot and element id.")
    Params = ActParams
    timeout_s = 45.0

    def available(self, env: Env) -> Availability:
        return _available(env)

    def resources(self, p: ActParams, env: Env) -> list[Resource]:
        seen, _node = _target(p, env)
        app_id = str(seen.window.get("app_id") or seen.app or "screen")  # "screen": a point in the whole screen
        names = (seen.app, app_id.rsplit(".", 1)[-1], str(seen.window.get("title") or ""))
        return [Resource(kind="app", value=app_id, access="write", role="target",
                         aliases=tuple(dict.fromkeys(n for n in names if n)))]

    def effects(self, p: ActParams, env: Env) -> Effects:
        seen, node = _target(p, env)
        return judge(p, node, seen.app)

    def describe(self, p: ActParams, env: Env) -> str:
        seen, node = _target(p, env)
        where = f" in {seen.app or seen.window.get('title') or 'a window'}"
        name = f"“{node['name']}”" if node and node.get("name") else (node or {}).get("role", "the element")
        if p.action == "click" and node is None:
            return f"Click at ({p.point[0]:.0f}, {p.point[1]:.0f}) in the picture{where}" if len(p.point) == 2 \
                else f"Click{where}"
        if p.action == "set_text":
            return f"Set {name} to “{_short(p.text)}”{where}"
        if p.action == "type":
            return f"Type “{_short(p.text)}” into {name}{where}"
        if p.action == "key":
            return f"Press {p.text or 'a key'}" + (f" in {name}" if node else "") + where
        if p.action == "scroll":
            return f"Scroll {name}{where}"
        return f"{p.action.capitalize()} {name}{where}"

    async def busy(self, p: ActParams, ctx: ActionContext) -> str:
        """Pointer and keys are shared with the person: while they use them, Mei waits (§10.3)."""
        desktop, bridge = ctx.env.desktop, ctx.env.bridge()
        if desktop is None or bridge is None:
            return ""
        if desktop.locked:
            return "Paused while the screen is locked"
        try:
            _seen, node = _target(p, ctx.env)
        except CapabilityError:
            return ""  # refused when it runs, with the reason
        if needs_input(p, node) and desktop.person_active(await bridge.idle_ms()):
            return "Paused while you use the computer"
        return ""

    async def run(self, p: ActParams, ctx: ActionContext) -> ActionResult:
        desktop = ctx.env.desktop
        assert desktop is not None
        seen, node = _target(p, ctx.env)
        if node is not None and node.get("role") == "password text" and p.action in ("set_text", "type"):
            field = node.get("name") or "the password field"
            return ActionResult(ok=True, observation="Handed this field to the person.", summary="Asked you to fill in a field",
                                handoff=HANDOFF.format(field=field, app=seen.app or "the window"))
        windows, monitors = await _screen(ctx.env)
        on_screen = seen.window.get("id") == SCREEN["id"]  # a point in the whole screen's picture: no window to find
        now = None if on_screen else next((w for w in windows if w.id == seen.window.get("id") and w.buffer), None)
        if now is None and not on_screen:
            raise CapabilityError("not_found", "that window has closed")
        from mei.computer.controller import DesktopError
        try:
            data = await _desktop(desktop.act(p.snapshot, p.action, element=p.element, point=p.point, text=p.text,
                                              window=window_dict(now) if now else None, monitors=monitors,
                                              needs_input=needs_input(p, node)), keep=("handoff",))
        except DesktopError as e:  # the worker looked at the focus just before typing: the person types it
            app = seen.app or "the window"
            handoff = HANDOFF.format(field="the password field", app=app) if "password" in e.message \
                else HANDOFF_UNSURE.format(text=_short(p.text, 60), app=app)
            return ActionResult(ok=True, observation=f"Handed this to the person: {e.message}.",
                                summary="Asked you to type something", handoff=handoff)
        changes = data.get("changes") or []
        observation = "Done. What changed:\n" + "\n".join(f"- {c}" for c in changes)
        if data.get("token"):
            observation += "\n\nThe window now:\n" + outline(data)
        return ActionResult(ok=True, observation=observation, summary=f"Used {seen.app or 'an app'}",
                            data_class="screen", trust="untrusted")


def judge(p: ActParams, node: dict | None, app: str) -> Effects:
    """What this act may do, from the element as observed (§10.4)."""
    role = (node or {}).get("role", "")
    if node is not None and role == "password text" and p.action in ("set_text", "type"):
        return READ_ONLY  # nothing is typed: the field goes to the person
    effects = UNKNOWN
    if node is not None:
        if p.action == "focus" or p.action == "scroll":
            effects = LOW_RISK
        elif p.action in ("set_text", "type") and role in TEXT_FIELDS and "\n" not in p.text:
            effects = LOW_RISK  # typing without submitting
        elif p.action == "key" and p.text.strip().lower() in SAFE_KEYS:
            effects = LOW_RISK
        elif p.action in ("press", "toggle") and (role in TOGGLES or role in OPENERS):
            effects = LOW_RISK  # the same act undoes it, and the change is observed
    elif p.action == "scroll":
        effects = LOW_RISK
    label = f"{(node or {}).get('name', '')} {p.text if p.action == 'key' else ''}"
    if OUTWARD.search(label) or MESSAGING.search(app):
        effects = msgspec.structs.replace(effects, visibility="others")
    return effects


def needs_input(p: ActParams, node: dict | None) -> bool:
    """Will the worker inject pointer or keyboard events (and so need the screen session and the
    control lease)? AT-SPI actions and EditableText ask the app itself."""
    if node is None:
        return True
    if p.action in ("press", "toggle"):
        return not node.get("actions")
    if p.action == "set_text":
        return not node.get("editable")
    return p.action != "focus"


def _target(p: ActParams, env: Env):
    desktop = env.desktop
    if desktop is None:
        raise CapabilityError("unavailable", "computer use isn't set up here")
    seen = desktop.seen(p.snapshot)
    if seen is None:
        raise CapabilityError("invalid", f"snapshot {p.snapshot} is no longer current: observe the window again "
                                         "and use the new ids")
    if not p.element:
        if p.action not in ("click", "scroll", "key", "type"):
            raise CapabilityError("invalid", f"{p.action} needs an element")
        if p.action in ("click", "scroll") and (len(p.point) != 2 or seen.picture is None):
            raise CapabilityError("invalid", f"{p.action} without an element needs a point in the snapshot's "
                                             "picture (observe with a picture first)")
        return seen, None
    node = seen.nodes.get(p.element)
    if node is None:
        raise CapabilityError("invalid", f"no element {p.element} in snapshot {p.snapshot}")
    return seen, node


async def _desktop(call, keep: tuple[str, ...] = ()):
    """The desktop's answer, its errors as the tool's; those in `keep` are raised as they are."""
    from mei.computer.controller import DesktopError
    try:
        return await call
    except DesktopError as e:
        if e.error in keep:
            raise
        error = {"stale": "invalid", "revoked": "unavailable", "handoff": "invalid"}.get(e.error, e.error)
        raise CapabilityError(error if error in ("invalid", "not_found", "unavailable", "failed", "timeout",
                                                 "permission") else "failed", e.message) from None


def _short(text: str, n: int = 40) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"

