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
    S.WAITING_INPUT: frozenset({S.RUNNING, S.INTERRUPTED, S.BLOCKED}),  # BLOCKED: "stop" at the step limit
    S.WAITING_RESOURCE: frozenset({S.RUNNING, S.INTERRUPTED}),
    S.VERIFYING: frozenset({S.RUNNING, S.COMPLETED, S.BLOCKED, S.INTERRUPTED}),
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


class Execution(StrEnum):
    """Whether an action ran (§7.3). Verification and effect disposition are separate fields."""

    PROPOSED = "PROPOSED"
    REJECTED = "REJECTED"  # its arguments didn't match the capability's schema
    POLICY_DENIED = "POLICY_DENIED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"  # its approval was overtaken by a steer or a cancel
    AUTHORIZED = "AUTHORIZED"
    SKIPPED = "SKIPPED"  # a steer or a cancel came before it started
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    IN_DOUBT = "IN_DOUBT"  # the runtime was lost after it started; the world may or may not have changed
    ABANDONED = "ABANDONED"


class Verification(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    UNVERIFIABLE = "unverifiable"


class Disposition(StrEnum):
    NONE = "none"  # nothing changed
    CONFIRMED = "confirmed"
    REVERTED = "reverted"
    UNKNOWN = "unknown"


E = Execution
ACTION_TERMINAL = frozenset({E.REJECTED, E.POLICY_DENIED, E.DENIED, E.EXPIRED, E.SUPERSEDED, E.SKIPPED,
                             E.SUCCEEDED, E.FAILED, E.CANCELLED, E.ABANDONED})

_ACTION_ALLOWED: dict[Execution, frozenset[Execution]] = {
    E.PROPOSED: frozenset({E.REJECTED, E.POLICY_DENIED, E.AWAITING_APPROVAL, E.AUTHORIZED, E.SKIPPED}),
    E.AWAITING_APPROVAL: frozenset({E.AUTHORIZED, E.DENIED, E.EXPIRED, E.SUPERSEDED}),
    # Back to AWAITING_APPROVAL when a one-time approval doesn't survive a restart (§15), or (also
    # POLICY_DENIED) when the re-check just before it runs finds its target changed.
    E.AUTHORIZED: frozenset({E.STARTED, E.SKIPPED, E.AWAITING_APPROVAL, E.POLICY_DENIED}),
    E.STARTED: frozenset({E.SUCCEEDED, E.FAILED, E.CANCELLED, E.IN_DOUBT}),
    E.IN_DOUBT: frozenset({E.SUCCEEDED, E.FAILED, E.ABANDONED, E.STARTED}),  # STARTED: an idempotent re-run
}


def check_action_transition(frm: Execution, to: Execution) -> None:
    if to not in _ACTION_ALLOWED.get(frm, frozenset()):
        raise InvalidTransition(f"action cannot go from {frm} to {to}")
