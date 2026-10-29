"""The desktop worker's protocol with the core: one JSON object per line on the worker's stdin
(commands) and stdout (events). Standard library only, because both sides import it: the core on the
runtime's Python and the worker on the system's.

Each message is a frozen dataclass named by `op`, and decoding checks every field's type, so neither
side acts on a malformed message. Commands that want an answer carry an `id`. The worker answers each
one with a `Reply` carrying the same `id`.
"""

import dataclasses
import json
import types
import typing
from dataclasses import dataclass, field

MAX_LINE = 16 * 1024 * 1024  # a screenshot travels as base64 in one line
VERSION = 1


class WireError(ValueError):
    pass


# ── Commands (core → worker) ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Observe:
    """A snapshot of a window's accessible tree, and optionally a picture of it. `windows` and
    `monitors` come from the Shell (ListWindows), which alone knows where windows are."""

    op: typing.ClassVar[str] = "observe"
    id: int
    window: dict  # the window to look at, as ListWindows gives it
    monitors: list = field(default_factory=list)
    image: bool = False
    max_nodes: int = 250
    screen: bool = False  # the whole screen, as a picture of every monitor (`window` is then ignored)


@dataclass(frozen=True)
class Act:
    """One action on an element of the current snapshot, or at a point of its picture."""

    op: typing.ClassVar[str] = "act"
    id: int
    token: str  # the snapshot the element id belongs to
    action: str  # press | set_text | type | toggle | focus | click | scroll | key
    element: str = ""  # "e12"
    point: list = field(default_factory=list)  # [x, y] in the snapshot's picture, for `click` without an element
    text: str = ""
    window: dict = field(default_factory=dict)  # where the window is now (it may have moved since the snapshot)
    monitors: list = field(default_factory=list)


@dataclass(frozen=True)
class OpenSession:
    """Start the RemoteDesktop session (pointer, keyboard, the screens' pictures). With a restore
    token the portal shows no dialog; without one it asks the person (setup does this once)."""

    op: typing.ClassVar[str] = "open_session"
    id: int
    restore_token: str = ""


@dataclass(frozen=True)
class CloseSession:
    op: typing.ClassVar[str] = "close_session"
    id: int


@dataclass(frozen=True)
class Lease:
    """The control token (§10.3): input may be injected until `valid_ms` from now. Renewed by the core
    every 250 ms while a task holds the computer. No reply."""

    op: typing.ClassVar[str] = "lease"
    generation: int
    valid_ms: int


@dataclass(frozen=True)
class Revoke:
    """Stop injecting input now and close the session. No reply."""

    op: typing.ClassVar[str] = "revoke"
    reason: str = ""


@dataclass(frozen=True)
class Quit:
    op: typing.ClassVar[str] = "quit"


# ── Events (worker → core) ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Ready:
    op: typing.ClassVar[str] = "ready"
    version: int
    accessibility: bool  # is the accessibility bus reachable?


@dataclass(frozen=True)
class Reply:
    op: typing.ClassVar[str] = "reply"
    id: int
    ok: bool
    data: dict = field(default_factory=dict)
    error: str = ""  # a capability error class: invalid | not_found | unavailable | failed | timeout | stale
    message: str = ""


@dataclass(frozen=True)
class Revoked:
    """The worker stopped input on its own: the Shell revoked control, the Shell went away, or the
    lease ran out."""

    op: typing.ClassVar[str] = "revoked"
    reason: str
    by: str = ""  # shell: the person (kill switch, chip) or the Shell going; lease: it ran out; core: the core asked


COMMANDS = {c.op: c for c in (Observe, Act, OpenSession, CloseSession, Lease, Revoke, Quit)}
EVENTS = {c.op: c for c in (Ready, Reply, Revoked)}


def encode(message) -> bytes:
    return (json.dumps({"op": message.op, **dataclasses.asdict(message)}, separators=(",", ":")) + "\n").encode()


def command(line: bytes | str):
    return _decode(line, COMMANDS)


def event(line: bytes | str):
    return _decode(line, EVENTS)


def _decode(line: bytes | str, kinds: dict):
    if len(line) > MAX_LINE:
        raise WireError("message too long")
    try:
        raw = json.loads(line)
    except ValueError as e:
        raise WireError(f"not JSON: {e}") from None
    if not isinstance(raw, dict) or raw.get("op") not in kinds:
        raise WireError(f"unknown message {str(raw)[:80]!r}")
    kind = kinds[raw.pop("op")]
    hints = typing.get_type_hints(kind)
    names = {f.name for f in dataclasses.fields(kind)}
    unknown = set(raw) - names
    if unknown:
        raise WireError(f"{kind.op}: unknown fields {sorted(unknown)}")
    for name, value in raw.items():
        if not _fits(value, hints[name]):
            raise WireError(f"{kind.op}.{name}: expected {hints[name]}, got {type(value).__name__}")
    try:
        return kind(**raw)
    except TypeError as e:  # a required field missing
        raise WireError(f"{kind.op}: {e}") from None


def _fits(value, hint) -> bool:
    origin = typing.get_origin(hint)
    if origin in (typing.Union, types.UnionType):
        return any(_fits(value, h) for h in typing.get_args(hint))
    if hint is type(None):
        return value is None
    base = origin or hint
    if base is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if base is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, base)
