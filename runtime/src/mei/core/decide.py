"""Deciding one proposed action (§8.2 `policy.evaluate`, §13.3 approval cards).

Validates the call against the capability's schema, works out what it would touch and where each
resource came from, asks the policy engine, and builds the card the person sees when it asks.
Pure apart from the reads it needs; the loop writes the outcome.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from mei.capabilities.base import Capability, CapabilityError, Effects, Env, Resource
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
    "needs_approval": "this changes something you didn't name",
}


@dataclass(frozen=True)
class Proposal:
    cap: Capability
    params: object
    canonical: str
    params_hash: str
    effects: Effects
    subjects: tuple[Subject, ...]
    description: str


class Refused(Exception):
    """The call can't even be judged: unknown tool, bad arguments, or nothing it names exists."""


def prepare(registry: Registry, env: Env, action, user_texts: list[str], untrusted: list[str]) -> Proposal:
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
    except CapabilityError as e:
        raise Refused(e.message) from None
    anchored = provenance.anchors(user_texts, env)
    subjects = tuple(Subject(kind=r.kind, value=r.value, access=r.access, role=r.role,
                             provenance=_provenance(r, anchored, user_texts, untrusted, env))
                     for r in resources)
    canonical, digest = registry.canonical(cap, params)
    return Proposal(cap, params, canonical, digest, effects, subjects, description)


def _provenance(r: Resource, anchored: list[Path], user_texts: list[str], untrusted: list[str], env: Env):
    if r.kind == "path":
        return provenance.classify(Path(r.value), anchored, untrusted, env)
    names = (r.value, *r.aliases)
    if any(_says(t, name) for t in user_texts for name in names):
        return "user"
    return "untrusted" if any(_says(t, r.value) for t in untrusted) else "model"


def _says(text: str, name: str) -> bool:
    """Does the text name this? Every word of the name appears in it ("make the text bigger" names
    "bigger text"); ids like org.gnome.Nautilus count as one word."""
    wanted = set(_WORD.findall(name.lower()))
    return bool(wanted) and wanted <= set(_WORD.findall(text.lower()))


_WORD = re.compile(r"\w+(?:[.-]\w+)*")  # "org.gnome.Nautilus" and "24-hour" are one word; "Files." is "files"


def judge(store: Store, env: Env, task, proposal: Proposal, preset_name: str) -> Decision:
    grants = [Grant(g["id"], g["capability"], tuple(GrantRule(**r) for r in json.loads(g["resources"])), g["task_id"])
              for g in agent.active_grants(store, task["id"])]
    facts = Facts(proposal.cap.name, proposal.cap.meta, proposal.effects, proposal.subjects, bool(task["tainted"]))
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
    reads_content = any(s.access == "read" for s in proposal.subjects) and proposal.cap.name == "fs.read_text"
    if reads_content and cloud:
        effects.append(f"What it reads is sent to {provider_label}")
    resources = [{"role": s.role, "kind": s.kind, "value": env.show(s.value) if s.kind == "path" else s.value,
                  "provenance": s.provenance} for s in proposal.subjects]
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
