"""Startup reconciliation (§15): what each task and action found mid-way becomes.

| Found                                  | Becomes                                                       |
|----------------------------------------|---------------------------------------------------------------|
| task ACCEPTED                          | started                                                       |
| model call in flight                   | task INTERRUPTED with its draft; never re-sent automatically  |
| action STARTED, no result              | IN_DOUBT: re-run if idempotent, else probed, else asked       |
| action AUTHORIZED by a one-time card   | asked again: that approval doesn't outlive the runtime        |
| action AUTHORIZED by policy or a grant | kept                                                          |
| action AWAITING_APPROVAL / a question  | still waiting                                                 |
| task CANCEL_REQUESTED                  | CANCELLED, with every open action settled                     |

A task that was running comes back INTERRUPTED (the person resumes it), unless it now waits for an
approval. Nothing is re-executed here; the loop does that on resume.
"""

import json

from mei.core.states import TERMINAL, Disposition, Execution, TaskState
from mei.store import agent, repo
from mei.store.db import Tx

from . import ledger

E, S = Execution, TaskState


def reconcile(tx: Tx, epoch: str) -> list[str]:
    """Settle everything the previous runtime left; returns the tasks to start now."""
    tx.execute("UPDATE turns SET state = 'lost' WHERE state = 'running' AND epoch != ?", (epoch,))
    marks = ",".join("?" for _ in TERMINAL)
    to_start: list[str] = []
    for row in tx.execute(f"SELECT * FROM tasks WHERE state NOT IN ({marks})", tuple(TERMINAL)).fetchall():
        state = S(row["state"])
        task = repo.task_dict(row)
        if state == S.ACCEPTED:
            to_start.append(row["id"])
            continue
        _in_doubt(tx, row["id"], epoch, cancelled=state == S.CANCEL_REQUESTED, task=task)
        if state == S.CANCEL_REQUESTED:
            ledger.cancel_now(tx, row["id"], draft=draft(tx, row["id"]))
        elif state in (S.RUNNING, S.VERIFYING, S.WAITING_RESOURCE):
            if state == S.RUNNING and _reask_one_time_approvals(tx, task):
                continue
            # The model call or an action was in flight. Don't re-send automatically: the upstream
            # call may already have been billed, and the person should see what happened first.
            final = repo.set_task_state(tx, row["id"], S.INTERRUPTED, error="Mei stopped while working on this")
            repo.finished_event(tx, final, draft=draft(tx, row["id"]))
    return to_start


def _in_doubt(tx: Tx, task_id: str, epoch: str, *, cancelled: bool, task: dict) -> None:
    for action in agent.task_actions(tx, task_id):
        if E(action["execution"]) != E.STARTED or action["epoch"] == epoch:
            continue
        if cancelled:
            mutating = (json.loads(action["effects"] or "{}")).get("mutates", "no") != "no"
            ledger.finish_action(tx, task, action, E.CANCELLED, "Stopped before it finished.", is_error=True,
                                 disposition=Disposition.UNKNOWN if mutating else Disposition.NONE)
        else:
            agent.update_action(tx, action["id"], E.IN_DOUBT)


def _reask_one_time_approvals(tx: Tx, task: dict) -> bool:
    asked = False
    for action in agent.task_actions(tx, task["id"]):
        if E(action["execution"]) != E.AUTHORIZED or not action["approval_id"]:
            continue
        approval = agent.get_approval(tx, action["approval_id"])
        if approval is not None and approval["scope"] in ("task", "always"):
            continue  # it came with a grant, which still holds
        ledger.reask(tx, task, action)
        asked = True
    return asked


def draft(tx: Tx, task_id: str) -> dict | None:
    turn = repo.latest_turn(tx, task_id)
    return None if turn is None else {"text": turn["draft_text"], "thinking": turn["draft_thinking"]}
