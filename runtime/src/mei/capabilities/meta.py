"""Tools that steer the task rather than the world: plan.update, ask_user, task.finish (§8.4, §8.5).

They go through the same ledger as every action (each call gets a result, so the transcript stays
valid), but the loop carries them out: they change the task's plan, wait for the person, or end
the task.
"""

from typing import Annotated, Literal

import msgspec

from .base import Capability, Env

# A criterion's typed check: one flat object, so every provider's schema dialect accepts it.
CheckType = Literal["file_exists", "file_absent", "dir_contains", "setting_equals", "window_present"]


class CheckSpec(msgspec.Struct, kw_only=True, omit_defaults=True):
    type: CheckType
    path: Annotated[str, msgspec.Meta(description="file_exists, file_absent, dir_contains: the path")] = ""
    glob: Annotated[str, msgspec.Meta(description="dir_contains: names to count, e.g. *.pdf")] = ""
    count: Annotated[int, msgspec.Meta(ge=-1, description="dir_contains: how many must match (-1: at least one)")] = -1
    min_size: Annotated[int, msgspec.Meta(ge=0, description="file_exists: smallest acceptable size in bytes")] = 0
    schema: Annotated[str, msgspec.Meta(description="setting_equals: GSettings schema")] = ""
    key: Annotated[str, msgspec.Meta(description="setting_equals: key")] = ""
    value: Annotated[str, msgspec.Meta(description="setting_equals: expected value as GVariant text, e.g. 'prefer-dark'")] = ""
    app_id: Annotated[str, msgspec.Meta(description="window_present: application id, e.g. org.gnome.Nautilus")] = ""
    title: Annotated[str, msgspec.Meta(description="window_present: text the window title contains")] = ""


class Step(msgspec.Struct, kw_only=True):
    text: str
    status: Literal["pending", "in_progress", "done", "skipped"] = "pending"


class Criterion(msgspec.Struct, kw_only=True, omit_defaults=True):
    text: Annotated[str, msgspec.Meta(description="What must be true when the task is done")]
    check: CheckSpec | None = None


class PlanParams(msgspec.Struct, kw_only=True):
    steps: list[Step] = msgspec.field(default_factory=list)
    criteria: Annotated[list[Criterion], msgspec.Meta(
        description="Acceptance criteria for the result. Give each a check when one fits; replaces earlier criteria")
    ] = msgspec.field(default_factory=list)


class PlanUpdate(Capability):
    name = "plan.update"
    summary = ("Record or update the plan for this task (steps with status) and its acceptance criteria. "
               "Call it before your first change, with criteria the runtime can check where possible.")
    Params = PlanParams
    meta = True
    idempotent = True

    def describe(self, p: PlanParams, env: Env) -> str:
        return "Update the plan"


class Field(msgspec.Struct, kw_only=True, omit_defaults=True):
    name: str
    label: str
    kind: Literal["text", "select", "checkbox", "date"] = "text"
    options: list[str] = msgspec.field(default_factory=list)


class AskParams(msgspec.Struct, kw_only=True):
    question: str
    choices: Annotated[list[str], msgspec.Meta(max_length=6, description="Buttons to answer with, if it's a choice")] = \
        msgspec.field(default_factory=list)
    fields: Annotated[list[Field], msgspec.Meta(max_length=8, description="A small form, if you need details")] = \
        msgspec.field(default_factory=list)


class AskUser(Capability):
    name = "ask_user"
    summary = "Ask the person a question and wait for the answer: free text, one of a few choices, or a small form."
    Params = AskParams
    meta = True
    idempotent = True

    def describe(self, p: AskParams, env: Env) -> str:
        return f"Ask: {p.question}"


class CriterionReport(msgspec.Struct, kw_only=True, omit_defaults=True):
    index: Annotated[int, msgspec.Meta(ge=0, description="Position of the criterion in the plan, from 0")]
    status: Literal["met", "not_met", "unknown"]
    note: str = ""


class FinishParams(msgspec.Struct, kw_only=True):
    summary: Annotated[str, msgspec.Meta(description="What you did and what the person should know, shown as your reply")]
    criteria: list[CriterionReport] = msgspec.field(default_factory=list)
    open_issues: list[str] = msgspec.field(default_factory=list)
    blocked: Annotated[bool, msgspec.Meta(description="True if you couldn't do the task")] = False


class TaskFinish(Capability):
    name = "task.finish"
    summary = ("Finish a task that changed anything: summarize, report each criterion, and list open issues. "
               "The runtime checks the criteria itself.")
    Params = FinishParams
    meta = True

    def describe(self, p: FinishParams, env: Env) -> str:
        return "Finish the task"
