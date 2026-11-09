"""One table that decides how every workflow failure is retried and reported.

Before this module the decision was spread over ``except`` clauses: a class's
position in the hierarchy decided whether it was retried, and the run's terminal
code was whichever handler caught it first. That is how an output-cap truncation
-- a request that cannot succeed unchanged -- inherited "retryable" from its
parent class and was sent twice. Here the policy is explicit per failure kind,
and the same classification feeds the retry loop, ``RunError``, and the client.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from backend.errors import (
    InvalidModelError,
    NodeTimeoutError,
    ProviderAuthenticationError,
    ProviderContentFilteredError,
    ProviderError,
    ProviderForbiddenError,
    ProviderInsufficientBalanceError,
    ProviderOutputTruncatedError,
    ProviderRequestRejectedError,
    RetryableProviderError,
    RunTimeoutError,
)
from backend.schemas import FailureCategory, RecoveryAction

#: Total attempts (first try included) for a transient failure of one call.
TRANSIENT_ATTEMPTS = 2

#: Ceiling on any single backoff wait, whatever ``Retry-After`` asks for.
MAX_BACKOFF_SECONDS = 20.0

#: Node -> the run stage a reader recognises.
NODE_STAGES: dict[str, str] = {
    "generator": "generation",
    "tech_reviewer": "review",
    "ux_reviewer": "review",
    "biz_reviewer": "review",
    "aggregator": "aggregation",
    "optimizer": "revision_planning",
}


@dataclass(frozen=True)
class FailureInfo:
    code: str
    message: str
    retryable: bool
    category: FailureCategory
    recovery_action: RecoveryAction


def is_transient(error: BaseException) -> bool:
    """True when the *same* request may succeed if sent again.

    Transport failures, 5xx, 429, an unfinished stream and a per-call timeout are
    transient. A truncation is never transient: the identical request needs the
    identical length. A run-level timeout is not either: there is no time left.
    """
    if isinstance(error, ProviderOutputTruncatedError):
        return False
    if isinstance(error, RunTimeoutError):
        return False
    if isinstance(error, RetryableProviderError):
        return True
    return isinstance(error, TimeoutError)


def backoff_seconds(error: BaseException, attempt: int, base: float) -> float:
    """Wait before attempt ``attempt + 1``: Retry-After if given, else exponential."""
    retry_after = getattr(error, "retry_after", None)
    if isinstance(retry_after, int | float) and retry_after > 0:
        return float(min(retry_after, MAX_BACKOFF_SECONDS))
    return float(min(base * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS))


def _resumable(has_best_version: bool) -> RecoveryAction:
    return (
        RecoveryAction.CONTINUE_FROM_BEST if has_best_version else RecoveryAction.RETRY
    )


def classify(error: BaseException, *, has_best_version: bool) -> FailureInfo:
    """Translate an exception into the stable, user-safe failure contract."""
    if isinstance(error, ProviderOutputTruncatedError):
        return FailureInfo(
            error.code,
            error.user_message,
            False,
            FailureCategory.OUTPUT_LIMIT,
            RecoveryAction.CONTINUE_FROM_BEST
            if has_best_version
            else RecoveryAction.REGENERATE_COMPACT,
        )
    if isinstance(
        error,
        ProviderAuthenticationError
        | InvalidModelError
        | ProviderForbiddenError
        | ProviderInsufficientBalanceError,
    ):
        return FailureInfo(
            error.code,
            error.user_message,
            False,
            FailureCategory.PERMANENT,
            RecoveryAction.CHECK_CONFIGURATION,
        )
    if isinstance(error, ProviderContentFilteredError | ProviderRequestRejectedError):
        return FailureInfo(
            error.code,
            error.user_message,
            False,
            FailureCategory.PERMANENT,
            RecoveryAction.EDIT_INPUT,
        )
    if isinstance(error, RetryableProviderError):
        return FailureInfo(
            error.code,
            error.user_message,
            True,
            FailureCategory.TRANSIENT,
            _resumable(has_best_version),
        )
    if isinstance(error, ProviderError):
        return FailureInfo(
            error.code,
            error.user_message,
            error.retryable,
            FailureCategory.TRANSIENT if error.retryable else FailureCategory.PERMANENT,
            _resumable(has_best_version)
            if error.retryable
            else RecoveryAction.CHECK_CONFIGURATION,
        )
    if isinstance(error, RunTimeoutError):
        return FailureInfo(
            "RUN_TIMEOUT",
            "The run exceeded its total time budget.",
            True,
            FailureCategory.INTERRUPTED,
            _resumable(has_best_version),
        )
    if isinstance(error, NodeTimeoutError | TimeoutError):
        return FailureInfo(
            "NODE_TIMEOUT",
            "A model call exceeded its timeout after retry.",
            True,
            FailureCategory.TRANSIENT,
            _resumable(has_best_version),
        )
    if isinstance(error, ValidationError):
        return FailureInfo(
            "STRUCTURED_OUTPUT_INVALID",
            "The provider returned invalid structured output.",
            True,
            FailureCategory.TRANSIENT,
            _resumable(has_best_version),
        )
    return FailureInfo(
        "WORKFLOW_FAILED",
        "The workflow could not complete.",
        False,
        FailureCategory.PERMANENT,
        _resumable(has_best_version),
    )


def tag(error: BaseException, **context: object) -> BaseException:
    """Attach workflow context to an exception without overwriting the origin.

    The first node to see an exception is the one it belongs to; the outer layers
    (LangGraph, the run wrapper) re-raise it and must not relabel it. Stored as an
    attribute because LangGraph re-raises the original exception object.
    """
    existing = getattr(error, "workflow_context", None)
    merged = dict(context)
    if isinstance(existing, dict):
        merged.update(existing)
    try:
        error.workflow_context = merged  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover - exceptions with __slots__
        pass
    return error


def context_of(error: BaseException) -> dict[str, object]:
    value = getattr(error, "workflow_context", None)
    return dict(value) if isinstance(value, dict) else {}
