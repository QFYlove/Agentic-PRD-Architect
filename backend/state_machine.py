from __future__ import annotations

from backend.schemas import RunStatus

TERMINAL_RUN_STATUSES = frozenset(
    {
        RunStatus.COMPLETED,
        RunStatus.MAX_ITERATIONS_REACHED,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    }
)

ALLOWED_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset(
        {
            RunStatus.GENERATING,
            RunStatus.CANCEL_REQUESTED,
            RunStatus.FAILED,
        }
    ),
    RunStatus.GENERATING: frozenset(
        {
            RunStatus.REVIEWING,
            RunStatus.PAUSE_REQUESTED,
            RunStatus.CANCEL_REQUESTED,
            RunStatus.FAILED,
        }
    ),
    RunStatus.REVIEWING: frozenset(
        {
            RunStatus.AGGREGATING,
            RunStatus.PAUSE_REQUESTED,
            RunStatus.CANCEL_REQUESTED,
            RunStatus.FAILED,
        }
    ),
    RunStatus.AGGREGATING: frozenset(
        {
            RunStatus.COMPLETED,
            RunStatus.MAX_ITERATIONS_REACHED,
            RunStatus.OPTIMIZING,
            RunStatus.PAUSE_REQUESTED,
            RunStatus.PAUSED,
            RunStatus.CANCEL_REQUESTED,
            RunStatus.FAILED,
        }
    ),
    RunStatus.OPTIMIZING: frozenset(
        {
            RunStatus.GENERATING,
            RunStatus.PAUSE_REQUESTED,
            RunStatus.CANCEL_REQUESTED,
            RunStatus.FAILED,
        }
    ),
    RunStatus.PAUSE_REQUESTED: frozenset(
        {
            RunStatus.PAUSED,
            RunStatus.COMPLETED,
            RunStatus.MAX_ITERATIONS_REACHED,
            RunStatus.CANCEL_REQUESTED,
            RunStatus.FAILED,
        }
    ),
    RunStatus.PAUSED: frozenset(
        {
            RunStatus.OPTIMIZING,
            RunStatus.CANCEL_REQUESTED,
            RunStatus.FAILED,
        }
    ),
    RunStatus.CANCEL_REQUESTED: frozenset(
        {
            RunStatus.CANCELLED,
            RunStatus.FAILED,
        }
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.MAX_ITERATIONS_REACHED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.FAILED: frozenset(),
}


def can_transition(current: RunStatus, target: RunStatus) -> bool:
    return target in ALLOWED_RUN_TRANSITIONS[current]


def require_transition(current: RunStatus, target: RunStatus) -> None:
    if not can_transition(current, target):
        raise ValueError(f"Illegal run status transition: {current} -> {target}")
