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

    kind: Literal["path", "app", "setting"]
    value: str
    access: Literal["read", "write"]
    role: str = ""
    provenance: Provenance = "model"


class GrantRule(msgspec.Struct, frozen=True, kw_only=True):
    kind: Literal["path", "app", "setting"]
    access: Literal["read", "write"]
    value: str  # a folder for paths (anything inside it matches); the exact value otherwise


@dataclass(frozen=True)
class Grant:
    id: str
    capability: str
    rules: tuple[GrantRule, ...]
    task_id: str | None  # None: it holds until revoked


@dataclass(frozen=True)
class Facts:
    capability: str
    meta: bool
    effects: Effects
    subjects: tuple[Subject, ...]
    tainted: bool


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
    if e.mutates == "no" and e.disclosure == "none":
        return Decision("allow", "read_only")
    if not facts.subjects:
        return _ask("no_resources", preset, floor=True)  # nothing to judge it by: never on autopilot
    grant = next((g for g in grants if covers(g, facts)), None)
    task_grant = grant if grant is not None and grant.task_id is not None else None
    if e.mutates == "unknown":
        return _granted(task_grant) or _ask("unknown_effect", preset, scopes=("once", "task"))
    if e.loses_data:
        return _ask("loses_data", preset, floor=True)
    untrusted = any(s.provenance == "untrusted" or (facts.tainted and s.provenance == "model") for s in facts.subjects)
    if e.visibility == "others":
        return _granted(task_grant) or _ask("visible_to_others", preset, scopes=("once", "task"))
    if e.disclosure == "off_machine":
        if untrusted:
            return _ask("untrusted_disclosure", preset, floor=True)
        return _granted(grant) or _ask("disclosure", preset, scopes=("once", "task"))
    writes = [Path(s.value) for s in facts.subjects if s.kind == "path" and s.access == "write"]
    if any(rules.protected(p) for p in writes):
        return _ask("protected_folder", preset, floor=True)
    if any(rules.runs_code(p) for p in writes):
        return _ask("runs_code", preset, floor=True)
    if grant is not None:
        return _granted(grant)
    if e.mutates == "local":
        if preset.allow_user_anchored and all(s.provenance == "user" for s in facts.subjects):
            return Decision("allow", "user_anchored")
        if preset.allow_model_in_home and all(_found_in_home(s, home) for s in facts.subjects):
            return Decision("allow", "hands_off")
    scopes: tuple[Scope, ...] = ("once", "task", "always") if e.mutates == "local" and e.undo == "recorded" \
        else ("once", "task")
    return _ask("needs_approval", preset, scopes=scopes)


def covers(grant: Grant, facts: Facts) -> bool:
    if grant.capability != facts.capability or not facts.subjects:
        return False
    return all(any(_matches(rule, s) for rule in grant.rules) for s in facts.subjects)


def rules_for(subjects: tuple[Subject, ...]) -> tuple[GrantRule, ...]:
    """What a grant made from this action covers: for paths, anything in the same folders."""
    return tuple(dict.fromkeys(
        GrantRule(kind=s.kind, access=s.access, value=str(Path(s.value).parent) if s.kind == "path" else s.value)
        for s in subjects))


def _matches(rule: GrantRule, s: Subject) -> bool:
    if rule.kind != s.kind or rule.access != s.access:
        return False
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
