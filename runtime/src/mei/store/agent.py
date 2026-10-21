"""The action ledger (§7): batches, actions, approvals, input requests, grants, and the task's plan.

Every change runs inside a caller's `Tx` and appends its durable event, so the UI's projection and
recovery both read the same history.
"""

import json

from mei.core.states import ACTION_TERMINAL, Execution, check_action_transition

from .db import Tx, new_id, now_ms

E = Execution
_DECIDED = frozenset({E.AUTHORIZED, E.AWAITING_APPROVAL, E.POLICY_DENIED, E.REJECTED})


def _one(src, sql: str, params: tuple = ()):
    return src.one(sql, params) if isinstance(src, Tx) else src.read_one(sql, params)


def _all(src, sql: str, params: tuple = ()) -> list:
    return src.execute(sql, params).fetchall() if isinstance(src, Tx) else src.read(sql, params)


def _loads(text: str | None):
    return json.loads(text) if text else None


def action_view(row) -> dict:
    """What the UI shows of an action: no observation content, which can be large and private."""
    result = _loads(row["result"]) or {}
    return {"id": row["id"], "task_id": row["task_id"], "batch_id": row["batch_id"], "position": row["position"],
            "tool": row["tool"], "capability": row["capability"], "description": row["description"],
            "execution": row["execution"], "verification": row["verification"], "disposition": row["disposition"],
            "decision": row["decision"], "decision_reason": row["decision_reason"], "error": row["error"],
            "summary": result.get("summary", ""), "effects": _loads(row["effects"]),
            "resources": json.loads(row["resources"]), "undo_recorded": bool(result.get("undo")),
            "created_at": row["created_at"], "finished_at": row["finished_at"]}


# ── Batches and actions ─────────────────────────────────────────────────────


def create_batch(tx: Tx, task: dict, message_id: str, calls: list[dict], seen_ordinal: int) -> str:
    """One batch per assistant message with tool calls; all its actions PROPOSED in this same
    transaction as the message (invariant 3). `seen_ordinal`: the last message the model had seen
    when it made these calls; anything the person sent after it is a steer."""
    batch_id = new_id()
    ts = now_ms()
    tx.execute("INSERT INTO batches (id, task_id, message_id, seen_ordinal, size, created_at) VALUES (?, ?, ?, ?, ?, ?)",
               (batch_id, task["id"], message_id, seen_ordinal, len(calls), ts))
    for position, call in enumerate(calls):
        action_id = new_id()
        tx.execute("INSERT INTO actions (id, task_id, batch_id, position, call_id, tool, arguments, execution, "
                   "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (action_id, task["id"], batch_id, position, call["id"], call["name"], call["arguments"],
                    E.PROPOSED, ts))
        _announce(tx, task["conversation_id"], "action.proposed", get_action(tx, action_id))
    return batch_id


def open_batch(src, task_id: str):
    """The task's batch with actions still to process, if any (there is at most one)."""
    return _one(src, "SELECT * FROM batches WHERE task_id = ? AND cursor < size ORDER BY created_at DESC LIMIT 1",
                (task_id,))


def batch_actions(src, batch_id: str) -> list:
    return _all(src, "SELECT * FROM actions WHERE batch_id = ? ORDER BY position", (batch_id,))


def task_actions(src, task_id: str) -> list:
    return _all(src, "SELECT * FROM actions WHERE task_id = ? ORDER BY created_at, position", (task_id,))


def get_action(src, action_id: str):
    return _one(src, "SELECT * FROM actions WHERE id = ?", (action_id,))


def update_action(tx: Tx, action_id: str, to: Execution, **fields) -> dict:
    """Move an action to `to` (checked against §7.3) and set other columns in the same write."""
    row = get_action(tx, action_id)
    frm = E(row["execution"])
    if frm != to:
        check_action_transition(frm, to)
    ts = now_ms()
    values = {"execution": to, **{k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in fields.items()}}
    if to == E.STARTED:
        values.setdefault("started_at", ts)
    if to in ACTION_TERMINAL:
        values.setdefault("finished_at", ts)
    tx.execute(f"UPDATE actions SET {', '.join(f'{k} = ?' for k in values)} WHERE id = ?", (*values.values(), action_id))
    updated = get_action(tx, action_id)
    kind = ("policy.decided" if frm == E.PROPOSED and to in _DECIDED else "action.started" if to == E.STARTED
            else "action.finished" if to in ACTION_TERMINAL else "action.updated")
    conversation_id = tx.one("SELECT conversation_id FROM tasks WHERE id = ?", (row["task_id"],))["conversation_id"]
    _announce(tx, conversation_id, kind, updated)
    return action_view(updated)


def advance_cursor(tx: Tx, batch_id: str, position: int) -> None:
    tx.execute("UPDATE batches SET cursor = MAX(cursor, ?) WHERE id = ?", (position + 1, batch_id))


def _announce(tx: Tx, conversation_id: str, kind: str, row) -> None:
    tx.event(kind, {"action": action_view(row)}, conversation_id=conversation_id, task_id=row["task_id"], required=False)


# ── Approvals ───────────────────────────────────────────────────────────────


def create_approval(tx: Tx, task: dict, action_id: str, params_hash: str, card: dict) -> dict:
    approval = {"id": new_id(), "task_id": task["id"], "action_id": action_id, "state": "pending", "card": card,
                "created_at": now_ms()}
    tx.execute("INSERT INTO approvals (id, task_id, action_id, params_hash, state, card, created_at) "
               "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
               (approval["id"], task["id"], action_id, params_hash, json.dumps(card), approval["created_at"]))
    # Required: a client that can't show approval cards must say it needs an update, not stall silently.
    tx.event("approval.requested", {"approval": approval}, conversation_id=task["conversation_id"], task_id=task["id"])
    return approval


def get_approval(src, approval_id: str):
    return _one(src, "SELECT * FROM approvals WHERE id = ?", (approval_id,))


def pending_approval(src, task_id: str):
    return _one(src, "SELECT * FROM approvals WHERE task_id = ? AND state = 'pending'", (task_id,))


def resolve_approval(tx: Tx, approval_id: str, state: str, *, scope: str | None = None,
                     decided_by: str | None = None) -> None:
    row = get_approval(tx, approval_id)
    tx.execute("UPDATE approvals SET state = ?, scope = ?, decided_by = ?, decided_at = ? WHERE id = ?",
               (state, scope, decided_by, now_ms(), approval_id))
    conversation_id = tx.one("SELECT conversation_id FROM tasks WHERE id = ?", (row["task_id"],))["conversation_id"]
    tx.event("approval.resolved", {"approval_id": approval_id, "action_id": row["action_id"], "state": state,
                                   "scope": scope}, conversation_id=conversation_id, task_id=row["task_id"])


def approval_view(row) -> dict:
    return {"id": row["id"], "task_id": row["task_id"], "action_id": row["action_id"], "state": row["state"],
            "card": json.loads(row["card"]), "created_at": row["created_at"]}


# ── Input requests ──────────────────────────────────────────────────────────


def create_input_request(tx: Tx, task: dict, kind: str, spec: dict, action_id: str | None = None) -> dict:
    request = {"id": new_id(), "task_id": task["id"], "action_id": action_id, "kind": kind, "spec": spec,
               "state": "pending", "created_at": now_ms()}
    tx.execute("INSERT INTO input_requests (id, task_id, action_id, kind, spec, state, created_at) "
               "VALUES (?, ?, ?, ?, ?, 'pending', ?)",
               (request["id"], task["id"], action_id, kind, json.dumps(spec), request["created_at"]))
    tx.event("input.requested", {"request": request}, conversation_id=task["conversation_id"], task_id=task["id"])
    return request


def get_input_request(src, request_id: str):
    return _one(src, "SELECT * FROM input_requests WHERE id = ?", (request_id,))


def pending_input(src, task_id: str):
    return _one(src, "SELECT * FROM input_requests WHERE task_id = ? AND state = 'pending'", (task_id,))


def close_input_request(tx: Tx, request_id: str, state: str, answer=None) -> None:
    row = get_input_request(tx, request_id)
    tx.execute("UPDATE input_requests SET state = ?, answer = ?, answered_at = ? WHERE id = ?",
               (state, json.dumps(answer) if answer is not None else None, now_ms(), request_id))
    conversation_id = tx.one("SELECT conversation_id FROM tasks WHERE id = ?", (row["task_id"],))["conversation_id"]
    tx.event("input.answered", {"request_id": request_id, "state": state}, conversation_id=conversation_id,
             task_id=row["task_id"])


def input_view(row) -> dict:
    return {"id": row["id"], "task_id": row["task_id"], "action_id": row["action_id"], "kind": row["kind"],
            "spec": json.loads(row["spec"]), "state": row["state"], "created_at": row["created_at"]}


# ── Plan ────────────────────────────────────────────────────────────────────


def set_plan(tx: Tx, task_id: str, plan: dict) -> None:
    tx.execute("UPDATE tasks SET plan = ?, updated_at = ? WHERE id = ?", (json.dumps(plan), now_ms(), task_id))
    conversation_id = tx.one("SELECT conversation_id FROM tasks WHERE id = ?", (task_id,))["conversation_id"]
    tx.event("plan.updated", {"task_id": task_id, "plan": plan}, conversation_id=conversation_id, task_id=task_id,
             required=False)


# ── Grants ──────────────────────────────────────────────────────────────────


def create_grant(tx: Tx, *, task_id: str | None, capability: str, rules: list[dict], description: str,
                 approval_id: str | None) -> dict:
    grant = {"id": new_id(), "task_id": task_id, "capability": capability, "rules": rules,
             "description": description, "created_at": now_ms()}
    tx.execute("INSERT INTO grants (id, task_id, capability, resources, description, approval_id, created_at) "
               "VALUES (?, ?, ?, ?, ?, ?, ?)",
               (grant["id"], task_id, capability, json.dumps(rules), description, approval_id, grant["created_at"]))
    tx.event("grant.created", {"grant": grant}, required=False)
    return grant


def active_grants(src, task_id: str) -> list:
    """Grants that can cover this task's actions: its own, and the persistent ones."""
    return _all(src, "SELECT * FROM grants WHERE revoked_at IS NULL AND (task_id = ? OR task_id IS NULL) "
                     "ORDER BY created_at", (task_id,))


def persistent_grants(src) -> list:
    return _all(src, "SELECT * FROM grants WHERE revoked_at IS NULL AND task_id IS NULL ORDER BY created_at")


def revoke_grant(tx: Tx, grant_id: str) -> bool:
    if tx.one("SELECT id FROM grants WHERE id = ? AND revoked_at IS NULL", (grant_id,)) is None:
        return False
    tx.execute("UPDATE grants SET revoked_at = ? WHERE id = ?", (now_ms(), grant_id))
    tx.event("grant.revoked", {"grant_id": grant_id}, required=False)
    return True


def grant_view(row) -> dict:
    return {"id": row["id"], "task_id": row["task_id"], "capability": row["capability"],
            "rules": json.loads(row["resources"]), "description": row["description"], "created_at": row["created_at"]}


# ── Snapshot ────────────────────────────────────────────────────────────────


def task_extras(src, task_id: str) -> dict:
    """What a conversation snapshot carries for a task beyond its state."""
    approval = pending_approval(src, task_id)
    request = pending_input(src, task_id)
    return {"actions": [action_view(a) for a in task_actions(src, task_id)],
            "approval": approval_view(approval) if approval else None,
            "input_request": input_view(request) if request else None}
