"""V2 reliability tests: retry policy, failure attribution, logging, recovery.

Covers PA-004 and PA-009. Each test names the defect it pins.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import pytest

from backend.errors import (
    NodeTimeoutError,
    ProviderAuthenticationError,
    ProviderOutputTruncatedError,
    RetryableProviderError,
    RunTimeoutError,
)
from backend.failures import backoff_seconds, classify, is_transient
from backend.observability import redact
from backend.providers.base import ProviderStructuredResult, ProviderTextEvent
from backend.providers.mock import MockLLMProvider
from backend.schemas import (
    CreateRunRequest,
    FailureCategory,
    NodeStatus,
    RecoveryAction,
    RecoveryMode,
    ReviewRole,
    RunSnapshot,
    RunStatus,
    TokenUsage,
)
from backend.tests.helpers import make_manager


@pytest.mark.parametrize(
    ("error", "transient"),
    [
        (RetryableProviderError("5xx"), True),
        (NodeTimeoutError(), True),
        (ProviderOutputTruncatedError("cap"), False),
        (RunTimeoutError(), False),
        (ProviderAuthenticationError("401"), False),
        (ValueError("bug"), False),
    ],
)
def test_only_failures_the_same_request_can_survive_are_transient(
    error: BaseException, transient: bool
) -> None:
    assert is_transient(error) is transient


def test_backoff_honours_retry_after_and_is_capped() -> None:
    assert backoff_seconds(RetryableProviderError("x", retry_after=3), 1, 1.0) == 3
    assert backoff_seconds(RetryableProviderError("x", retry_after=999), 1, 1.0) == 20
    assert backoff_seconds(RetryableProviderError("x"), 1, 1.0) == 1.0
    assert backoff_seconds(RetryableProviderError("x"), 3, 1.0) == 4.0


@pytest.mark.parametrize(
    ("error", "code", "retryable", "category", "action"),
    [
        (
            ProviderOutputTruncatedError("cap"),
            "PROVIDER_OUTPUT_TRUNCATED",
            False,
            FailureCategory.OUTPUT_LIMIT,
            RecoveryAction.CONTINUE_FROM_BEST,
        ),
        (
            ProviderAuthenticationError("401"),
            "PROVIDER_AUTHENTICATION_FAILED",
            False,
            FailureCategory.PERMANENT,
            RecoveryAction.CHECK_CONFIGURATION,
        ),
        (
            RunTimeoutError(),
            "RUN_TIMEOUT",
            True,
            FailureCategory.INTERRUPTED,
            RecoveryAction.CONTINUE_FROM_BEST,
        ),
        (
            NodeTimeoutError(),
            "NODE_TIMEOUT",
            True,
            FailureCategory.TRANSIENT,
            RecoveryAction.CONTINUE_FROM_BEST,
        ),
        (
            KeyError("bug"),
            "WORKFLOW_FAILED",
            False,
            FailureCategory.PERMANENT,
            RecoveryAction.CONTINUE_FROM_BEST,
        ),
    ],
)
def test_every_failure_has_a_code_a_category_and_a_next_step(
    error: BaseException,
    code: str,
    retryable: bool,
    category: FailureCategory,
    action: RecoveryAction,
) -> None:
    info = classify(error, has_best_version=True)

    assert (info.code, info.retryable, info.category, info.recovery_action) == (
        code,
        retryable,
        category,
        action,
    )


def test_a_truncation_with_no_version_offers_a_compact_regeneration() -> None:
    info = classify(ProviderOutputTruncatedError("cap"), has_best_version=False)
    assert info.recovery_action is RecoveryAction.REGENERATE_COMPACT


class FlakyThenWorkingProvider(MockLLMProvider):
    """The first stream breaks off at the transport; the second works."""

    def __init__(self) -> None:
        super().__init__(delays_enabled=False)
        self.calls = 0

    async def stream_prd(self, **kwargs: Any) -> AsyncIterator[ProviderTextEvent]:  # type: ignore[override]
        self.calls += 1
        if self.calls == 1:
            raise RetryableProviderError("transport")
            yield  # pragma: no cover - makes this an async generator
        async for event in super().stream_prd(**kwargs):
            yield event


async def test_a_transient_generation_failure_is_retried_once_and_recovers() -> None:
    provider = FlakyThenWorkingProvider()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product with one flaky call.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert provider.calls == 3  # v1 twice, v2 once
    assert result.error is None


class OneReviewerFails(MockLLMProvider):
    """UX fails after the other two reviewers have both started.

    BIZ starts last, so the old "last node marked RUNNING" attribution would
    have blamed it.
    """

    def __init__(self, role: ReviewRole) -> None:
        super().__init__(delays_enabled=False)
        self.role = role
        self.started: list[ReviewRole] = []
        self.all_started = asyncio.Event()

    async def generate_review(self, **kwargs: Any) -> ProviderStructuredResult:  # type: ignore[override]
        role = kwargs["role"]
        self.started.append(role)
        if len(self.started) == 3:
            self.all_started.set()
        if role is self.role:
            await asyncio.wait_for(self.all_started.wait(), timeout=1)
            raise ProviderAuthenticationError("Injected")
        await asyncio.sleep(0.2)
        return await super().generate_review(**kwargs)


@pytest.mark.parametrize("failing", list(ReviewRole))
async def test_the_failed_parallel_reviewer_is_the_one_that_raised(
    failing: ReviewRole,
) -> None:
    manager = make_manager(provider=OneReviewerFails(failing))
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product with one failing reviewer.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    node = f"{failing.value}_reviewer"
    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.node == node
    assert result.error.stage == "review"
    assert result.error.version == 1
    assert result.node_statuses[node] is NodeStatus.FAILED
    # The siblings were cancelled with it; none of them is left spinning.
    for other in ReviewRole:
        if other is not failing:
            assert result.node_statuses[f"{other.value}_reviewer"] in {
                NodeStatus.SKIPPED,
                NodeStatus.SUCCEEDED,
            }
    # v1 itself is complete, so it is not an incomplete draft.
    assert result.incomplete_draft is None
    assert [version.version for version in result.versions] == [1]


class InvalidTwiceProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__(delays_enabled=False)
        self.reviews = 0
        self.repairs = 0

    async def generate_review(self, **kwargs: Any) -> ProviderStructuredResult:  # type: ignore[override]
        if kwargs["role"] is ReviewRole.TECH:
            self.reviews += 1
            return ProviderStructuredResult(
                value={"role": "tech", "summary": "x"},
                usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
                model="m",
            )
        return await super().generate_review(**kwargs)

    async def repair_structured(self, **kwargs: Any) -> ProviderStructuredResult:  # type: ignore[override]
        self.repairs += 1
        return ProviderStructuredResult(
            value={"still": "invalid"},
            usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
            model="m",
        )


async def test_schema_repair_runs_exactly_once_then_fails_with_its_node() -> None:
    provider = InvalidTwiceProvider()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product with an invalid review.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "STRUCTURED_OUTPUT_INVALID"
    assert result.error.node == "tech_reviewer"
    assert provider.reviews == 1
    assert provider.repairs == 1


class ExplodingAggregatorInput(MockLLMProvider):
    async def generate_revision_plan(self, **kwargs: Any) -> ProviderStructuredResult:  # type: ignore[override]
        raise KeyError("unexpected internal state")


async def test_an_unknown_exception_is_logged_with_node_trace_and_redacted_stack(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="agentic_prd.workflow")
    manager = make_manager(provider=ExplodingAggregatorInput(delays_enabled=False))
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product whose optimizer explodes.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "WORKFLOW_FAILED"
    assert result.error.node == "optimizer"
    assert result.error.trace_id == result.trace_id
    # The user-facing message stays generic.
    assert "unexpected internal state" not in result.error.message
    failures = [
        json.loads(record.message)
        for record in caplog.records
        if '"event":"workflow_failed"' in record.message
    ]
    assert len(failures) == 1
    logged = failures[0]
    assert logged["node"] == "optimizer"
    assert logged["trace_id"] == result.trace_id
    assert logged["exception_type"] == "KeyError"
    assert "Traceback" in logged["stack"]
    assert logged["provider"]


def test_redaction_masks_credential_shapes() -> None:
    text = (
        "Authorization: Bearer abcdefghijklmnop api_key=sk-livekey123456 "
        'password: "hunter2hunter2"'
    )
    masked = redact(text)

    assert "abcdefghijklmnop" not in masked
    assert "livekey123456" not in masked
    assert "hunter2hunter2" not in masked


async def test_run_failed_event_carries_the_structured_error() -> None:
    manager = make_manager(provider=OneReviewerFails(ReviewRole.UX))
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product with a structured failure.")
    )
    await manager.wait_for_completion(created.run_id, wait_seconds=5)

    events = manager.event_store.replay(created.run_id, 0)
    failed = next(event for event in events if event.event.value == "run_failed")

    assert failed.payload["error_code"] == "PROVIDER_AUTHENTICATION_FAILED"
    assert failed.payload["error"]["node"] == "ux_reviewer"
    assert failed.payload["error"]["recovery_action"] == "check_configuration"
    assert failed.payload["node_statuses"]["ux_reviewer"] == "FAILED"


async def test_history_returns_durable_events_without_deltas() -> None:
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product whose history is replayable.")
    )
    await manager.wait_for_completion(created.run_id, wait_seconds=5)

    history = manager.history(created.run_id)

    assert history
    assert all(event.event.value != "prd_delta" for event in history)
    assert [event.sequence for event in history] == sorted(
        event.sequence for event in history
    )


def test_a_legacy_snapshot_without_v2_fields_still_loads() -> None:
    from pathlib import Path

    payload = json.loads(
        (
            Path(__file__).parents[2] / "contracts" / "v1" / "run_snapshot.json"
        ).read_text(encoding="utf-8")
    )
    snapshot = RunSnapshot.model_validate(payload)

    assert snapshot.trace_id is None
    assert snapshot.incomplete_draft is None
    assert snapshot.generation_mode.value == "standard"
    for version in snapshot.versions:
        if version.evaluation is not None:
            assert version.evaluation.tech.is_legacy_scoring


async def test_restart_recovery_mode_keeps_the_original_input() -> None:
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product that is run again from scratch.",
            target_audience="Testers",
        )
    )
    source = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    recovered = await manager.create_recovery_run(source.run_id, RecoveryMode.RESTART)
    result = await manager.wait_for_completion(recovered.run_id, wait_seconds=5)

    assert result.user_idea == source.user_idea
    assert result.target_audience == "Testers"
    assert result.seed_prd is None
    assert result.source_run_id == source.run_id
    summaries = {item.run_id: item for item in await manager.list_runs(limit=10)}
    assert summaries[recovered.run_id].source_run_id == source.run_id
    assert isinstance(summaries[source.run_id].run_id, UUID)
