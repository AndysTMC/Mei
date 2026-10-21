"""Transaction helpers the loop and the engine's commands share.

Every terminal action gets exactly one tool-result message, written in the same transaction that
makes it terminal and advances the batch cursor, so the stored transcript is always valid for every
provider (invariants 3 and 4).
"""

import json

from mei.core.states import ACTION_TERMINAL, Disposition, Execution, TaskState
from mei.obs import redact
from mei.store import agent, repo
from mei.store.db import Store, Tx

E = Execution
MAX_STORED_OBSERVATION = 100_000


def finish_action(tx: Tx, task: dict, action, to: Execution, observation: str, *, is_error: bool,
                  **fields) -> dict:
    """Make `action` terminal, store the result the model will see, and move the cursor past it."""
    view = agent.update_action(tx, action["id"], to, **fields)
    repo.add_message(tx, task["conversation_id"], "tool", redact(observation)[:MAX_STORED_OBSERVATION],
                     task_id=task["id"], action_id=action["id"], metadata={"is_error": is_error})
    agent.advance_cursor(tx, action["batch_id"], action["position"])
    return view


def skip_rest(tx: Tx, task: dict, batch_id: str, why: str) -> None:
    """Every action of the batch not yet started ends here (§8.1 steer, §8.7 cancel)."""
    for action in agent.batch_actions(tx, batch_id):
        state = E(action["execution"])
        if state in ACTION_TERMINAL or state in (E.STARTED, E.IN_DOUBT):
            continue
        if state == E.AWAITING_APPROVAL:
            approval = agent.pending_approval(tx, task["id"])
            if approval is not None:
                agent.resolve_approval(tx, approval["id"], "superseded")
            finish_action(tx, task, action, E.SUPERSEDED, f"Not done: {why}.", is_error=True)
        else:
            finish_action(tx, task, action, E.SKIPPED, f"Skipped: {why}.", is_error=True)
    request = agent.pending_input(tx, task["id"])
    if request is not None:
        agent.close_input_request(tx, request["id"], "superseded")


def steer_pending(src, task_id: str, seen_ordinal: int) -> bool:
    """Has the person written in this task since the model last looked?"""
    sql = "SELECT 1 FROM messages WHERE task_id = ? AND role = 'user' AND ordinal > ? LIMIT 1"
    row = src.one(sql, (task_id, seen_ordinal)) if isinstance(src, Tx) else src.read_one(sql, (task_id, seen_ordinal))
    return row is not None


def last_ordinal(store: Store, conversation_id: str) -> int:
    row = store.read_one("SELECT COALESCE(MAX(ordinal), 0) AS n FROM messages WHERE conversation_id = ?",
                         (conversation_id,))
    return int(row["n"])


def cancel_now(tx: Tx, task_id: str, *, draft: dict | None = None, error: str | None = None) -> dict:
    """Stop a task that has no action in flight: settle its batch and inputs, then CANCELLED."""
    task = repo.task_dict(repo.get_task(tx, task_id))
    batch = agent.open_batch(tx, task_id)
    if batch is not None:
        skip_rest(tx, task, batch["id"], "the person stopped the task")
    request = agent.pending_input(tx, task_id)
    if request is not None:
        agent.close_input_request(tx, request["id"], "superseded")
    if TaskState(task["state"]) != TaskState.CANCEL_REQUESTED:
        repo.set_task_state(tx, task_id, TaskState.CANCEL_REQUESTED)
    task = repo.set_task_state(tx, task_id, TaskState.CANCELLED, error=error)
    repo.finished_event(tx, task, draft=draft)
    return task


def mutated(src, task_id: str) -> bool:
    """Did any action of this task change something?"""
    for action in agent.task_actions(src, task_id):
        effects = json.loads(action["effects"]) if action["effects"] else {}
        if action["execution"] == E.SUCCEEDED and effects.get("mutates", "no") != "no" \
                and action["disposition"] != Disposition.NONE:
            return True
    return False


def request_approval(tx: Tx, task: dict, action_id: str, params_hash: str, card: dict) -> dict:
    approval = agent.create_approval(tx, task, action_id, params_hash, card)
    tx.execute("UPDATE actions SET approval_id = ? WHERE id = ?", (approval["id"], action_id))
    if TaskState(repo.get_task(tx, task["id"])["state"]) != TaskState.WAITING_APPROVAL:
        repo.set_task_state(tx, task["id"], TaskState.WAITING_APPROVAL)
    return approval


def reask(tx: Tx, task: dict, action) -> None:
    """The approval no longer holds (its params changed, or it was for one go and Mei restarted)."""
    old = agent.get_approval(tx, action["approval_id"]) if action["approval_id"] else None
    card = json.loads(old["card"]) if old else {"title": action["description"], "capability": action["capability"],
                                                "resources": json.loads(action["resources"]), "effects": [],
                                                "scopes": ["once"], "default_scope": "once",
                                                "scope_text": {"once": "Allow once"}}
    agent.update_action(tx, action["id"], E.AWAITING_APPROVAL)
    request_approval(tx, task, action["id"], action["params_hash"], card)


IN_DOUBT_CHOICES = ("It happened", "It didn't happen", "I'm not sure")


def ask_in_doubt(tx: Tx, task: dict, action) -> None:
    spec = {"question": f"Mei restarted while doing this: “{action['description']}”. Did it happen?",
            "choices": list(IN_DOUBT_CHOICES), "fields": []}
    agent.create_input_request(tx, task, "in_doubt", spec, action_id=action["id"])
    repo.set_task_state(tx, task["id"], TaskState.WAITING_INPUT)
