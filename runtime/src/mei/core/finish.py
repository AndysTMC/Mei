"""The meta tools, carried out by the loop (§8.4, §8.5): plan.update, ask_user, task.finish.

Finishing runs every typed criterion check against the world as it is now. A failed check goes back
to the model once; after that the task completes as partially verified with the failure listed.
Criteria without a check are only ever "reported". The outcome badge claims no more than that.
"""

import copy
import json
from dataclasses import dataclass
from typing import Literal

import msgspec

from mei.capabilities.base import CheckResult, Env
from mei.capabilities.checks import run_check
from mei.capabilities.meta import AskParams, CheckSpec, FinishParams, PlanParams
from mei.core.states import Disposition, Execution, TaskState
from mei.store import agent, repo
from mei.store.db import Tx

from .ledger import finish_action, skip_rest

E = Execution
S = TaskState
STEERED = "Not finished yet: the person sent a new message while Mei checked. Read it, then finish."
NUDGE = ("You changed things in this task but didn't call task_finish. Call it now: summarize, report each "
         "criterion by index, and list open issues.")


def save_plan(tx: Tx, task: dict, action, p: PlanParams) -> None:
    plan = {"steps": [msgspec.to_builtins(s) for s in p.steps],
            "criteria": [{"text": c.named(), "check": msgspec.to_builtins(c.check) if c.check and c.check.type is not None else None,
                          "status": "pending"} for c in p.criteria if c.named()]}
    agent.update_action(tx, action["id"], E.STARTED)
    agent.set_plan(tx, task["id"], plan)
    finish_action(tx, task, action, E.SUCCEEDED, "Plan saved.", is_error=False,
                  result={"ok": True, "summary": "Updated the plan"})


def ask(tx: Tx, task: dict, action, p: AskParams) -> None:
    spec = {"question": p.question, "choices": list(p.choices), "fields": [msgspec.to_builtins(f) for f in p.fields]}
    agent.create_input_request(tx, task, "question", spec, action_id=action["id"])
    repo.set_task_state(tx, task["id"], S.WAITING_INPUT)


def answer_text(spec: dict, value) -> str:
    if isinstance(value, dict):
        return "The person answered:\n" + "\n".join(f"- {k}: {v}" for k, v in value.items())
    return f"The person answered: {value}"


@dataclass(frozen=True)
class Checked:
    index: int
    text: str
    check: dict | None
    result: CheckResult | None


async def run_checks(plan: dict, env: Env) -> list[Checked]:
    out = []
    for i, criterion in enumerate(plan.get("criteria") or []):
        spec = criterion.get("check")
        result = await run_check(msgspec.convert(spec, CheckSpec), env) if spec else None
        out.append(Checked(i, criterion.get("text", ""), spec, result))
    return out


def failures_text(failed: list[Checked]) -> str:
    lines = [f"- {c.index}. {c.text}: {c.result.detail}" for c in failed if c.result]
    return ("Mei checked the criteria and these failed:\n" + "\n".join(lines) +
            "\nFix what you can and call task_finish again, or list what's left in open_issues.")


OutcomeKind = Literal["outcome_verified", "partially_verified", "reported"]


def outcome(checked: list[Checked], p: FinishParams | None, *, note: str = "") -> dict:
    reports = {r.index: r for r in (p.criteria if p else [])}
    criteria = []
    for c in checked:
        report = reports.get(c.index)
        status = c.result.status if c.result else "reported"
        criteria.append({"index": c.index, "text": c.text, "check": c.check["type"] if c.check else None,
                         "status": status, "detail": c.result.detail if c.result else "",
                         "reported": report.status if report else None, "note": report.note if report else ""})
    passed = sum(1 for c in criteria if c["status"] == "passed")
    failed = any(c["status"] == "failed" for c in criteria)
    kind: OutcomeKind
    if failed or (0 < passed < len(criteria)):
        kind = "partially_verified"
    elif criteria and passed == len(criteria):
        kind = "outcome_verified"
    else:
        kind = "reported"
    return {"kind": kind, "summary": p.summary if p else "", "criteria": criteria,
            "open_issues": list(p.open_issues) if p else [], "note": note}


def complete(tx: Tx, task: dict, result: dict, *, text: str, blocked: bool = False) -> None:
    """End the task with its outcome, and show the summary as Mei's reply."""
    if text:
        repo.add_message(tx, task["conversation_id"], "assistant", text, task_id=task["id"],
                         metadata={"outcome": result["kind"]})
    tx.execute("UPDATE tasks SET outcome = ? WHERE id = ?", (json.dumps(result), task["id"]))
    final = repo.set_task_state(tx, task["id"], S.BLOCKED if blocked else S.COMPLETED,
                                error=text if blocked else None)
    repo.finished_event(tx, final, outcome=result)


def finished(tx: Tx, task: dict, action, p: FinishParams, checked: list[Checked]) -> None:
    result = outcome(checked, p)
    finish_action(tx, task, action, E.SUCCEEDED, "Finished.", is_error=False, disposition=Disposition.NONE,
                  result={"ok": True, "summary": "Finished the task"})
    skip_rest(tx, task, action["batch_id"], "the task was finished")
    plan = copy.deepcopy(task["plan"])
    for c in result["criteria"]:
        if c["index"] < len(plan.get("criteria") or []):
            plan["criteria"][c["index"]]["status"] = c["status"]
    agent.set_plan(tx, task["id"], plan)
    complete(tx, task, result, text=p.summary, blocked=p.blocked)
