"""The policy engine (§13.2): a pure function from an action's facts to allow, ask, or deny.

Rows are checked top to bottom and the first that matches decides. Presets are parameter sets for
the rows that may vary; the floor rows are code no preset reaches, so a setting can't switch one off.
A decision says which approval scopes the card may offer: floor cases only ever offer "once".
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import msgspec

from mei.capabilities.base import Effects

from .paths import PathRules, inside
from .provenance import Provenance

POLICY_VERSION = "1"
Scope = Literal["once", "task", "always"]


@dataclass(frozen=True)
class Preset:
    name: Literal["cautious", "balanced", "hands_off"]
    allow_user_anchored: bool  # local changes to things the person named go ahead without a card
    allow_model_in_home: bool  # …and to things the model found inside home (not from untrusted content)
    default_scope: Scope  # what the card suggests


PRESETS = {p.name: p for p in (
    Preset("cautious", allow_user_anchored=False, allow_model_in_home=False, default_scope="once"),
    Preset("balanced", allow_user_anchored=True, allow_model_in_home=False, default_scope="once"),
    Preset("hands_off", allow_user_anchored=True, allow_model_in_home=True, default_scope="task"),
)}


class Subject(msgspec.Struct, frozen=True, kw_only=True):
    """A resource as policy sees it."""

    kind: Literal["path", "app", "setting", "memory", "screen"]
    value: str
    access: Literal["read", "write"]
    role: str = ""
    provenance: Provenance = "model"
    named: bool = False  # the person named this item itself, not only a folder holding it
    label: str = ""  # how people know it, when its value is an id (a memory's text)


class GrantRule(msgspec.Struct, frozen=True, kw_only=True):
    kind: Literal["path", "app", "setting", "memory", "screen"]
    access: Literal["read", "write"]
    value: str  # a folder for paths (things directly in it match, not deeper); the exact value otherwise
    tree: bool = False  # for a folder a command works in: the folder itself and everything inside it


@dataclass(frozen=True)
class Grant:
    id: str
    capability: str
    rules: tuple[GrantRule, ...]
    task_id: str | None  # None: it holds until revoked
    discloses: bool = False  # made on a card that said data would leave this computer (decision 0031)


@dataclass(frozen=True)
class Facts:
    capability: str
    meta: bool
    effects: Effects
    subjects: tuple[Subject, ...]
    tainted: bool
    always_ask: bool = False  # the capability asks every time (shell.run_host)
    # Looking at the screen needs no asking: the person's screen switch is on (decision 0039), however
    # the request came (typed, Live or "Hey Mei").
    screen_ok: bool = False


@dataclass(frozen=True)
class Decision:
    decision: Literal["allow", "ask", "deny"]
    reason: str  # a stable code, recorded with the decision
    grant_id: str | None = None
    scopes: tuple[Scope, ...] = ()  # what an approval card may offer
    default_scope: Scope = "once"
    version: str = POLICY_VERSION


def evaluate(facts: Facts, preset: Preset, grants: list[Grant], rules: PathRules, home: Path) -> Decision:
    e = facts.effects
    paths = [Path(s.value) for s in facts.subjects if s.kind == "path"]
    if facts.meta:
        return Decision("allow", "meta")
    if any(rules.denied(p) for p in paths):
        return Decision("deny", "hard_deny")
    if any(rules.sensitive(p) for p in paths):
        return _ask("sensitive", preset, floor=True)
    if facts.always_ask:
        return _ask("host_command", preset, floor=True)
    if any(s.kind == "screen" for s in facts.subjects):
        # Seeing the screen (decision 0039): asked unless the screen switch is on.
        if facts.screen_ok:
            return Decision("allow", "screen_ok")
        return _granted(next((g for g in grants if covers(g, facts)), None)) \
            or _ask("sees_screen", preset, scopes=("once", "task", "always"))
    if e.mutates == "no" and e.disclosure == "none":
        return Decision("allow", "read_only")
    if not facts.subjects:
        return _ask("no_resources", preset, floor=True)  # nothing to judge it by: never on autopilot
    # Floors come before anything that could allow: whatever else the action does (loses data, has an
    # unknown effect, is seen by others), writing a folder Mei protects or one that runs code asks
    # each time, and no grant covers it.
    writes = [Path(s.value) for s in facts.subjects if s.kind == "path" and s.access == "write"]
    if any(rules.protected(p) for p in writes):
        return _ask("protected_folder", preset, floor=True)
    if any(rules.runs_code(p) for p in writes):
        return _ask("runs_code", preset, floor=True)
    grant = next((g for g in grants if covers(g, facts)), None)
    task_grant = grant if grant is not None and grant.task_id is not None else None
    untrusted = any(s.provenance == "untrusted" or (facts.tainted and s.provenance == "model") for s in facts.subjects)
    # Every restriction must pass, not the first that a grant matches (decision 0031): sending data off
    # this computer is judged before anything a grant made for something else could allow.
    if e.disclosure == "off_machine":
        if untrusted:
            return _ask("untrusted_disclosure", preset, floor=True)
        sending = next((g for g in grants if g.discloses and covers(g, facts)), None)
        if sending is None:
            return _ask("disclosure", preset, scopes=("once", "task"))
        grant = sending
        task_grant = sending if sending.task_id is not None else None
    if e.mutates == "unknown":
        return _granted(task_grant) or _ask("unknown_effect", preset, scopes=("once", "task"))
    if e.loses_data:  # never on autopilot or by a standing grant; the person can grant a folder for the task
        return _granted(task_grant) or _ask("loses_data", preset, scopes=("once", "task"))
    if e.visibility == "others":
        return _granted(task_grant) or _ask("visible_to_others", preset, scopes=("once", "task"))
    if grant is not None:
        return _granted(grant)
    if e.mutates == "local":
        # Once the task has read a document (tainted), a folder the person named no longer vouches for
        # everything in it: content can steer the model toward "everything else in this folder". Only
        # what they named exactly goes ahead; the rest asks, and a task grant covers the batch.
        if preset.allow_user_anchored and all(s.provenance == "user" and (s.named or not facts.tainted)
                                              for s in facts.subjects):
            return Decision("allow", "user_anchored")
        if not facts.tainted and preset.allow_model_in_home and all(_found_in_home(s, home) for s in facts.subjects):
            return Decision("allow", "hands_off")
    scopes: tuple[Scope, ...] = ("once", "task", "always") if e.mutates == "local" and e.undo == "recorded" \
        else ("once", "task")
    theirs = all(s.provenance == "user" for s in facts.subjects)
    # Why it asks, truthfully: everything here was named by the person, so it's the setting asking.
    reason = "after_reading" if facts.tainted and theirs else "asks_first" if theirs else "needs_approval"
    return _ask(reason, preset, scopes=scopes)


def covers(grant: Grant, facts: Facts) -> bool:
    if grant.capability != facts.capability or not facts.subjects:
        return False
    return all(any(_matches(rule, s) for rule in grant.rules) for s in facts.subjects)


def rules_for(subjects: tuple[Subject, ...]) -> tuple[GrantRule, ...]:
    """What a grant made from this action covers: for paths, things in the same folders (for a command's
    folders, the folders themselves)."""
    return tuple(dict.fromkeys(_rule(s) for s in subjects))


TREE_ROLES = frozenset({"folder", "workspace", "cwd"})  # a command's folders: granted as the folder itself


def _rule(s: Subject) -> GrantRule:
    if s.kind != "path":
        return GrantRule(kind=s.kind, access=s.access, value=s.value)
    if s.role in TREE_ROLES:
        return GrantRule(kind="path", access=s.access, value=s.value, tree=True)
    return GrantRule(kind="path", access=s.access, value=str(Path(s.value).parent))


def _matches(rule: GrantRule, s: Subject) -> bool:
    if rule.kind != s.kind or rule.access != s.access:
        return False
    if s.kind == "path" and rule.tree:
        return inside(Path(s.value), Path(rule.value))
    if s.kind == "path":
        return Path(s.value).parent == Path(rule.value)  # things in that folder, not the folder or deeper
    return rule.value == s.value


def _found_in_home(s: Subject, home: Path) -> bool:
    if s.provenance == "user":
        return True
    return s.provenance == "model" and (s.kind != "path" or inside(Path(s.value), home))


def _granted(grant: Grant | None) -> Decision | None:
    return Decision("allow", "granted", grant_id=grant.id) if grant is not None else None


def _ask(reason: str, preset: Preset, *, floor: bool = False, scopes: tuple[Scope, ...] = ("once", "task")) -> Decision:
    offered: tuple[Scope, ...] = ("once",) if floor else scopes
    default: Scope = preset.default_scope if preset.default_scope in offered else "once"
    return Decision("ask", reason, scopes=offered, default_scope=default)
