"""Condition A: one generator call, with the product generator's retry policy."""

from __future__ import annotations

import asyncio
import time
from contextlib import aclosing
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from backend.errors import ProviderError, RetryableProviderError
from backend.language import detect_output_language
from backend.prd_document import validate_generated_prd
from backend.providers.base import LLMProvider
from backend.schemas import CreateRunRequest, TokenUsage


@dataclass
class AttemptResult:
    attempt: int
    outcome: Literal["ok", "retryable_error", "error"]
    error_code: str | None
    seconds: float


@dataclass
class SingleResult:
    status: Literal["completed", "failed"]
    content: str | None
    error_code: str | None
    output_language: str
    started_at: str
    ended_at: str
    wall_seconds: float
    attempts: list[AttemptResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def error_code(error: BaseException) -> str:
    if isinstance(error, ProviderError):
        return error.code
    if isinstance(error, TimeoutError):
        # The workflow maps every timeout to this code; A uses the same one.
        return "RUN_TIMEOUT"
    return f"HARNESS_ERROR:{type(error).__name__}"


async def _attempt(
    provider: LLMProvider,
    request: CreateRunRequest,
    output_language: str,
    timeout_seconds: float,
) -> str:
    content = ""
    usage: TokenUsage | None = None
    finish_reason: str | None = None
    async with asyncio.timeout(timeout_seconds):
        stream = provider.stream_prd(
            user_idea=request.user_idea,
            target_audience=request.target_audience,
            user_constraints=request.user_constraints,
            iteration=1,
            revision_plan=None,
            baseline_prd=None,
            output_language=output_language,
        )
        async with aclosing(stream) as events:  # type: ignore[type-var]
            async for event in events:
                content += event.delta
                if event.usage is not None:
                    usage = event.usage
                if event.finish_reason:
                    finish_reason = event.finish_reason
    # Same order as the workflow: completeness first, then metering.
    validated = validate_generated_prd(content, finish_reason)
    if usage is None:
        raise RetryableProviderError("Provider omitted token usage")
    return validated


async def run_condition_a(
    request: CreateRunRequest,
    provider: LLMProvider,
    *,
    max_attempts: int = 2,
    attempt_timeout_seconds: float = 240,
) -> SingleResult:
    """Generate once, retrying exactly as the workflow's generator node does.

    Up to ``max_attempts`` tries; only ``RetryableProviderError`` (which
    includes the incomplete-output errors) and timeouts are retried, with no
    backoff. Any other provider error ends the run immediately.
    """
    output_language = detect_output_language(
        request.user_idea, request.target_audience, request.user_constraints
    )
    started_at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    attempts: list[AttemptResult] = []
    content: str | None = None
    final_code: str | None = None
    for attempt in range(1, max_attempts + 1):
        attempt_started = time.monotonic()
        try:
            content = await _attempt(
                provider, request, output_language, attempt_timeout_seconds
            )
        except (RetryableProviderError, TimeoutError) as error:
            final_code = error_code(error)
            attempts.append(
                AttemptResult(
                    attempt,
                    "retryable_error",
                    final_code,
                    round(time.monotonic() - attempt_started, 3),
                )
            )
            continue
        except Exception as error:
            final_code = error_code(error)
            attempts.append(
                AttemptResult(
                    attempt,
                    "error",
                    final_code,
                    round(time.monotonic() - attempt_started, 3),
                )
            )
            break
        attempts.append(
            AttemptResult(
                attempt, "ok", None, round(time.monotonic() - attempt_started, 3)
            )
        )
        final_code = None
        break
    return SingleResult(
        status="completed" if content is not None else "failed",
        content=content,
        error_code=None if content is not None else final_code,
        output_language=output_language,
        started_at=started_at,
        ended_at=datetime.now(UTC).isoformat(),
        wall_seconds=round(time.monotonic() - started, 3),
        attempts=attempts,
    )
