"""Deciding one proposed action (§8.2 `policy.evaluate`, §13.3 approval cards).

Validates the call against the capability's schema, works out what it would touch and where each
resource came from, asks the policy engine, and builds the card the person sees when it asks.
Pure apart from the reads it needs; the loop writes the outcome.
"""

import json
import os
import re
from dataclasses import dataclass, replace

import msgspec
from pathlib import Path

from mei.capabilities.base import WORKSPACE, Capability, CapabilityError, Effects, Env, Resource
from mei.capabilities.registry import InvalidArguments, Registry
from mei.policy import provenance
from mei.policy.engine import PRESETS, Decision, Facts, Grant, GrantRule, Subject, evaluate, rules_for
from mei.store import agent
from mei.store.db import Store

MAX_REASON_CHARS = 400
REPEAT_LIMIT = 2  # a third identical call is refused (§8.2 repetition guard)

_REASONS = {
    "hard_deny": "Mei never lets a tool touch this (keys, keyrings, browser profiles, or Mei's own data)",
    "sensitive": "this may hold passwords or keys",
    "no_resources": "Mei can't tell what this would change",
    "unknown_effect": "Mei can't tell what this would change",
    "loses_data": "this can't be undone",
    "visible_to_others": "other people would see this",
    "untrusted_disclosure": "this would send something a file or page suggested off this computer",
    "disclosure": "this sends data off this computer",
    "protected_folder": "this changes a whole top-level folder",
    "runs_code": "a file written here runs later (at login or in a terminal)",
    "host_command": "this runs on your computer outside Mei's sandbox",
    "needs_approval": "this changes something you didn't name",
    "asks_first": "your approval setting asks before Mei changes things",
    "after_reading": "Mei read a document in this task, and you didn't name this exactly",
}


@dataclass(frozen=True)
class Proposal:
    cap: Capability
    params: object
    canonical: str
    params_hash: str
    effects: Effects
    subjects: tuple[Subject, ...]  # paths as they really resolve
    description: str
    content: tuple[str, ...] = ()  # paths whose contents the result will carry


@dataclass(frozen=True)
class Seen:
    """What a decision may go by: the person's words in this task, and what Mei has read in it."""

    user_texts: list[str]
    untrusted_content: list[str]  # file contents and the like: where instructions hide
    untrusted_other: list[str]  # listings and search results
    workspace: Path | None = None  # the conversation's scratch folder: Mei's own, granted by design


class Refused(Exception):
    """The call can't even be judged: unknown tool, bad arguments, or nothing it names exists."""


def prepare(registry: Registry, env: Env, action, seen: Seen) -> Proposal:
    cap = registry.by_wire(action["tool"])
    if cap is None:
        raise Refused(f"There is no tool called {action['tool']}.")
    try:
        params = registry.decode(cap, action["arguments"])
    except InvalidArguments as e:
        raise Refused(str(e)) from None
    available = cap.available(env)
    if not available.ok:
        raise Refused(f"{action['tool']} isn't available: {available.reason}")
    try:
        resources = cap.resources(params, env)
        effects = cap.effects(params, env)
        description = cap.describe(params, env)
        content = tuple(str(_real(c)) if isinstance(c, Path) else c for c in cap.reads_content(params, env))
    except CapabilityError as e:
        raise Refused(e.message) from None
    anchored = provenance.resolved_anchors(provenance.anchors(seen.user_texts, env))
    subjects = tuple(_subject(r, anchored, seen, env) for r in resources)
    canonical, digest = registry.canonical(cap, params)
    return Proposal(cap, params, canonical, digest, effects, subjects, description, content)


def for_provider(proposal: Proposal, *, cloud: bool, cloud_files: str) -> Proposal:
    """Reading a file the person didn't point at, for a cloud model under "Files I point to", is a
    disclosure: it asks, and once they allow it the contents may go (§13.5). Under "Never" nothing
    is sent anyway, and under "Any file" nothing needs asking."""
    if not (cloud and cloud_files == "pointed" and proposal.content):
        return proposal
    pointed = all(any(s.value == c and s.provenance == "user" for s in proposal.subjects) for c in proposal.content)
    effects = msgspec.structs.replace(proposal.effects, disclosure="off_machine")
    return proposal if pointed else replace(proposal, effects=effects)


def _subject(r: Resource, anchored: list[Path], seen: Seen, env: Env) -> Subject:
    if r.kind != "path":
        names = (r.value, *r.aliases)
        if any(_says(t, name) for t in seen.user_texts for name in names):
            where = "user"
        else:
            where = "untrusted" if any(_says(t, r.value) for t in seen.untrusted_content) else "model"
        return Subject(kind=r.kind, value=r.value, access=r.access, role=r.role, provenance=where,
                       named=where == "user", label=r.aliases[0] if r.aliases else "")
    if r.value == WORKSPACE or (seen.workspace and provenance.inside(_real(Path(r.value)), _real(seen.workspace))):
        value = seen.workspace if r.value == WORKSPACE else Path(r.value)
        return Subject(kind="path", value=str(_real(value)), access=r.access, role=r.role, provenance="user",
                       named=True)
    path = Path(r.value)
    is_named = provenance.named(path, anchored, seen.user_texts)
    where = provenance.classify(path, anchored, seen.untrusted_content, seen.untrusted_other, env, is_named=is_named)
    # Judged, recorded, and granted by where it really leads, not by how the model spelled it.
    return Subject(kind="path", value=str(_real(path)), access=r.access, role=r.role, provenance=where,
                   named=is_named)


def _real(path: Path) -> Path:
    return Path(os.path.realpath(path))


def _says(text: str, name: str) -> bool:
    """Does the text name this? Every word of the name appears in it ("make the text bigger" names
    "bigger text"); ids like org.gnome.Nautilus count as one word."""
    wanted = set(_WORD.findall(name.lower()))
    return bool(wanted) and wanted <= set(_WORD.findall(text.lower()))


_WORD = re.compile(r"\w+(?:[.-]\w+)*")  # "org.gnome.Nautilus" and "24-hour" are one word; "Files." is "files"


def judge(store: Store, env: Env, task, proposal: Proposal, preset_name: str) -> Decision:
    grants = [Grant(g["id"], g["capability"], tuple(GrantRule(**r) for r in json.loads(g["resources"])), g["task_id"])
              for g in agent.active_grants(store, task["id"])]
    facts = Facts(proposal.cap.name, proposal.cap.meta, proposal.effects, proposal.subjects, bool(task["tainted"]),
                  always_ask=proposal.cap.always_ask)
    return evaluate(facts, PRESETS.get(preset_name, PRESETS["balanced"]), grants, env.rules, env.home)


def repeated(store: Store, task_id: str, action_id: str, capability: str, params_hash: str) -> bool:
    row = store.read_one("SELECT COUNT(*) AS n FROM actions WHERE task_id = ? AND id != ? AND capability = ? "
                         "AND params_hash = ?", (task_id, action_id, capability, params_hash))
    return int(row["n"]) >= REPEAT_LIMIT


def refusal_text(decision: Decision) -> str:
    return f"Not allowed: {_REASONS.get(decision.reason, decision.reason)}. Don't try another way around it."


def card(env: Env, proposal: Proposal, decision: Decision, *, why: str, read_from: list[str],
         provider_label: str, cloud: bool) -> dict:
    """What the approval card shows (§13.3): the action in words, what it touches and where each
    thing came from, its effects in plain words, the model's stated reason, and what it read first."""
    e = proposal.effects
    effects = []
    if e.mutates == "local":
        effects.append("Changes things on this computer" + (" (can be undone)" if e.undo == "recorded" else ""))
    elif e.mutates == "unknown":
        effects.append("Mei can't tell what this will change")
    elif e.mutates == "external":
        effects.append("Changes something outside this computer")
    if e.loses_data:
        effects.append("Can destroy data that can't be recovered")
    if e.visibility == "others":
        effects.append("Other people will see the result")
    if e.disclosure == "off_machine":
        effects.append("Sends data off this computer")
    if proposal.content and cloud:
        effects.append(f"What it reads is sent to {provider_label}")
    resources = [{"role": s.role, "kind": s.kind, "provenance": s.provenance,
                  "value": env.show(s.value) if s.kind == "path" else s.label or s.value} for s in proposal.subjects]
    scope_text = {"once": "Allow once"}
    if "task" in decision.scopes:
        scope_text["task"] = _grant_text(env, proposal, "for the rest of this task")
    if "always" in decision.scopes:
        scope_text["always"] = _grant_text(env, proposal, "from now on")
    return {"title": proposal.description, "capability": proposal.cap.name, "why": why[:MAX_REASON_CHARS],
            "why_is_models": True, "reason": decision.reason, "reason_text": _REASONS.get(decision.reason, ""),
            "resources": resources, "effects": effects, "read_from": [env.show(p) for p in read_from][:5],
            "scopes": list(decision.scopes), "default_scope": decision.default_scope, "scope_text": scope_text}


def _grant_text(env: Env, proposal: Proposal, when: str) -> str:
    folders = [env.show(r.value) for r in rules_for(proposal.subjects) if r.kind == "path"]
    verb = proposal.cap.name.split(".")[-1].replace("_", " ")
    where = " and ".join(dict.fromkeys(folders)) if folders else "these"
    return f"Allow {verb} in {where} {when}"
