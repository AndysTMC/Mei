import pytest

from mei.core.states import (ACTION_TERMINAL, TERMINAL, Execution, InvalidTransition, TaskState, can_transition,
                             check_action_transition, check_transition)

S = TaskState
E = Execution


@pytest.mark.parametrize("frm,to", [
    (S.ACCEPTED, S.RUNNING), (S.RUNNING, S.COMPLETED), (S.RUNNING, S.WAITING_APPROVAL),
    (S.WAITING_APPROVAL, S.RUNNING), (S.RUNNING, S.VERIFYING), (S.VERIFYING, S.COMPLETED),
    (S.RUNNING, S.INTERRUPTED), (S.INTERRUPTED, S.RUNNING), (S.INTERRUPTED, S.CANCELLED),
    (S.RUNNING, S.CANCEL_REQUESTED), (S.CANCEL_REQUESTED, S.CANCELLED), (S.ACCEPTED, S.CANCELLED),
    (S.RUNNING, S.FAILED), (S.CANCEL_REQUESTED, S.FAILED),
])
def test_allowed(frm, to):
    check_transition(frm, to)


@pytest.mark.parametrize("frm,to", [
    (S.ACCEPTED, S.COMPLETED), (S.CANCEL_REQUESTED, S.RUNNING), (S.CANCEL_REQUESTED, S.INTERRUPTED),
    (S.WAITING_INPUT, S.COMPLETED), (S.INTERRUPTED, S.COMPLETED), (S.RUNNING, S.ACCEPTED),
])
def test_forbidden(frm, to):
    with pytest.raises(InvalidTransition):
        check_transition(frm, to)


def test_terminal_states_are_final():
    for frm in TERMINAL:
        assert not any(can_transition(frm, to) for to in S)


def test_every_non_terminal_state_can_be_stopped_or_fail():
    for frm in S:
        if frm in TERMINAL:
            continue
        assert can_transition(frm, S.FAILED)
        assert frm == S.CANCEL_REQUESTED or can_transition(frm, S.CANCEL_REQUESTED)


@pytest.mark.parametrize("frm,to", [
    (E.PROPOSED, E.AUTHORIZED), (E.PROPOSED, E.AWAITING_APPROVAL), (E.PROPOSED, E.REJECTED),
    (E.PROPOSED, E.POLICY_DENIED), (E.AWAITING_APPROVAL, E.AUTHORIZED), (E.AWAITING_APPROVAL, E.SUPERSEDED),
    (E.AUTHORIZED, E.STARTED), (E.AUTHORIZED, E.SKIPPED), (E.AUTHORIZED, E.AWAITING_APPROVAL),
    (E.STARTED, E.SUCCEEDED), (E.STARTED, E.IN_DOUBT), (E.IN_DOUBT, E.ABANDONED), (E.IN_DOUBT, E.STARTED),
])
def test_action_allowed(frm, to):
    check_action_transition(frm, to)


@pytest.mark.parametrize("frm,to", [
    (E.PROPOSED, E.STARTED),  # nothing starts without a recorded authorization (invariant 2)
    (E.AWAITING_APPROVAL, E.STARTED), (E.STARTED, E.SKIPPED), (E.SUCCEEDED, E.FAILED), (E.IN_DOUBT, E.SKIPPED),
])
def test_action_forbidden(frm, to):
    with pytest.raises(InvalidTransition):
        check_action_transition(frm, to)


def test_terminal_actions_are_final():
    for frm in ACTION_TERMINAL:
        for to in E:
            with pytest.raises(InvalidTransition):
                check_action_transition(frm, to)
