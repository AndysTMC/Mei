"""Task state machine (architecture §7.2). Pure: no I/O, used by the store before every change."""

from enum import StrEnum


class TaskState(StrEnum):
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    WAITING_INPUT = "WAITING_INPUT"
    WAITING_RESOURCE = "WAITING_RESOURCE"
    VERIFYING = "VERIFYING"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    INTERRUPTED = "INTERRUPTED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


S = TaskState
TERMINAL = frozenset({S.COMPLETED, S.BLOCKED, S.CANCELLED, S.FAILED})
WAITING = frozenset({S.WAITING_APPROVAL, S.WAITING_INPUT, S.WAITING_RESOURCE})

_ALLOWED: dict[TaskState, frozenset[TaskState]] = {
    S.ACCEPTED: frozenset({S.RUNNING, S.CANCELLED}),
    S.RUNNING: frozenset({*WAITING, S.VERIFYING, S.COMPLETED, S.BLOCKED, S.INTERRUPTED}),
    S.WAITING_APPROVAL: frozenset({S.RUNNING, S.INTERRUPTED}),
    S.WAITING_INPUT: frozenset({S.RUNNING, S.INTERRUPTED}),
    S.WAITING_RESOURCE: frozenset({S.RUNNING, S.INTERRUPTED}),
    S.VERIFYING: frozenset({S.RUNNING, S.COMPLETED, S.INTERRUPTED}),
    S.CANCEL_REQUESTED: frozenset({S.CANCELLED}),
    S.INTERRUPTED: frozenset({S.RUNNING, S.CANCELLED}),
}
# From any non-terminal state a task may be asked to stop or may fail outright.
for _state in S:
    if _state not in TERMINAL and _state is not S.CANCEL_REQUESTED:
        _ALLOWED[_state] = _ALLOWED.get(_state, frozenset()) | {S.CANCEL_REQUESTED, S.FAILED}
_ALLOWED[S.CANCEL_REQUESTED] |= {S.FAILED}


class InvalidTransition(ValueError):
    pass


def can_transition(frm: TaskState, to: TaskState) -> bool:
    return to in _ALLOWED.get(frm, frozenset())


def check_transition(frm: TaskState, to: TaskState) -> None:
    if not can_transition(frm, to):
        raise InvalidTransition(f"task cannot go from {frm} to {to}")
