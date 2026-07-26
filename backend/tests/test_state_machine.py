import pytest

from backend.schemas import RunStatus
from backend.state_machine import (
    ALLOWED_RUN_TRANSITIONS,
    TERMINAL_RUN_STATUSES,
    can_transition,
    require_transition,
)


def test_terminal_states_have_no_outgoing_transitions() -> None:
    for status in TERMINAL_RUN_STATUSES:
        assert ALLOWED_RUN_TRANSITIONS[status] == frozenset()


def test_happy_path_transitions_are_allowed() -> None:
    path = [
        RunStatus.QUEUED,
        RunStatus.GENERATING,
        RunStatus.REVIEWING,
        RunStatus.AGGREGATING,
        RunStatus.OPTIMIZING,
        RunStatus.GENERATING,
        RunStatus.REVIEWING,
        RunStatus.AGGREGATING,
        RunStatus.COMPLETED,
    ]

    for current, target in zip(path, path[1:], strict=False):
        assert can_transition(current, target)


def test_illegal_transition_is_rejected() -> None:
    assert not can_transition(RunStatus.QUEUED, RunStatus.COMPLETED)

    with pytest.raises(ValueError, match="Illegal run status transition"):
        require_transition(RunStatus.QUEUED, RunStatus.COMPLETED)


def test_cancel_path_is_allowed_from_active_state() -> None:
    require_transition(RunStatus.REVIEWING, RunStatus.CANCEL_REQUESTED)
    require_transition(RunStatus.CANCEL_REQUESTED, RunStatus.CANCELLED)


@pytest.mark.parametrize(
    "status",
    [
        RunStatus.GENERATING,
        RunStatus.REVIEWING,
        RunStatus.AGGREGATING,
        RunStatus.OPTIMIZING,
    ],
)
def test_pause_request_is_allowed_from_active_work(status: RunStatus) -> None:
    require_transition(status, RunStatus.PAUSE_REQUESTED)


@pytest.mark.parametrize(
    "status",
    [status for status in RunStatus if status not in TERMINAL_RUN_STATUSES],
)
def test_cancel_request_is_allowed_from_every_non_terminal_state(
    status: RunStatus,
) -> None:
    if status is RunStatus.CANCEL_REQUESTED:
        require_transition(status, RunStatus.CANCELLED)
    else:
        require_transition(status, RunStatus.CANCEL_REQUESTED)


@pytest.mark.parametrize("status", list(TERMINAL_RUN_STATUSES))
def test_terminal_state_cannot_transition_to_running(status: RunStatus) -> None:
    assert not can_transition(status, RunStatus.GENERATING)
