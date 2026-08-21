from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from backend.errors import RetryableProviderError
from backend.language import DEFAULT_OUTPUT_LANGUAGE
from backend.providers.base import ProviderStructuredResult, ProviderTextEvent
from backend.providers.mock import MockLLMProvider
from backend.run_manager import RunManager
from backend.schemas import (
    CreateRunRequest,
    FeedbackItem,
    FeedbackSeverity,
    ResumeRunRequest,
    ReviewRole,
    RoleReview,
    RunEventType,
    RunStatus,
)
from backend.tests.helpers import make_manager, make_settings


class SeverityProvider(MockLLMProvider):
    """A mock whose reviewers raise exactly the severities a test asks for.

    The quality gate is a conjunction of a score and a blocking-findings count,
    so testing either half requires pinning the other.
    """

    def __init__(self, severities: dict[int, list[FeedbackSeverity]]) -> None:
        super().__init__(delays_enabled=False)
        self.severities = severities

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> ProviderStructuredResult:
        result = await super().generate_review(
            role=role,
            prd=prd,
            iteration=iteration,
            output_language=output_language,
        )
        review = RoleReview.model_validate(result.value)
        wanted = self.severities.get(iteration, [])
        result.value = review.model_copy(
            update={
                "feedback": [
                    FeedbackItem(
                        severity=severity,
                        issue=f"{role.value} {severity.value} at v{iteration}",
                        recommendation="Close the gap in the named section.",
                    )
                    for severity in wanted
                ]
            }
        ).model_dump(mode="json")
        return result


class NoBlockerProvider(SeverityProvider):
    """Reviewers that only ever raise advice, so the score alone decides."""

    def __init__(self) -> None:
        super().__init__(dict.fromkeys(range(1, 6), [FeedbackSeverity.SHOULD_FIX]))


async def wait_for_status(
    manager: object,
    run_id: object,
    statuses: set[RunStatus],
    *,
    wait_seconds: float = 3,
) -> RunStatus:
    from backend.run_manager import RunManager

    assert isinstance(manager, RunManager)
    async with asyncio.timeout(wait_seconds):
        while True:
            status = (await manager.get_run(run_id)).status  # type: ignore[arg-type]
            if status in statuses:
                return status
            await asyncio.sleep(0.001)


async def test_mock_happy_path_completes_in_two_iterations() -> None:
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(
            user_idea=("Build a podcast micro-subscription that charges per episode.")
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert result.current_iteration == 2
    assert [version.evaluation.overall_score for version in result.versions] == [
        71.0,
        88.0,
    ]
    assert result.estimated_cost_usd == 0
    assert result.total_tokens.total_tokens > 0


async def test_high_threshold_reaches_distinct_max_iteration_terminal() -> None:
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a detailed product that needs iterative review.",
            quality_threshold=100,
            max_iterations=3,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.MAX_ITERATIONS_REACHED
    assert result.current_iteration == 3
    assert len(result.versions) == 3


@pytest.mark.parametrize(
    ("threshold", "expected_iterations"),
    [(70, 1), (71, 1), (71.1, 2)],
)
async def test_quality_gate_includes_equal_boundary(
    threshold: float,
    expected_iterations: int,
) -> None:
    """`>=` not `>`, isolated from the blocking half of the gate.

    The default mock raises one `must_fix` per reviewer on the first round, which
    would hold every run to iteration 2 and hide the boundary being tested here.
    """
    manager = make_manager(provider=NoBlockerProvider())
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product with an exact quality boundary.",
            quality_threshold=threshold,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert result.current_iteration == expected_iterations


@pytest.mark.parametrize("max_iterations", [1, 3, 5])
async def test_generator_never_exceeds_requested_maximum(
    max_iterations: int,
) -> None:
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product with a strict iteration maximum.",
            quality_threshold=100,
            max_iterations=max_iterations,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.MAX_ITERATIONS_REACHED
    assert len(result.versions) == max_iterations


class ParallelTrackingProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__(delays_enabled=False)
        self.started: set[ReviewRole] = set()
        self.all_started = asyncio.Event()

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ):
        self.started.add(role)
        if len(self.started) == 3:
            self.all_started.set()
        await asyncio.wait_for(self.all_started.wait(), timeout=1)
        return await super().generate_review(
            role=role,
            prd=prd,
            iteration=iteration,
            output_language=output_language,
        )


async def test_three_reviewers_start_in_parallel() -> None:
    provider = ParallelTrackingProvider()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product with parallel review.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert provider.started == set(ReviewRole)


async def test_pause_waits_for_safe_point_and_resume_keeps_user_override() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        generator_delay=0.001,
        reviewer_delay=0.03,
        optimizer_delay=0.001,
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a pausable product workflow.")
    )
    await wait_for_status(manager, created.run_id, {RunStatus.REVIEWING})

    requested = await manager.request_pause(created.run_id)
    assert requested.status is RunStatus.PAUSE_REQUESTED
    await wait_for_status(manager, created.run_id, {RunStatus.PAUSED})
    paused = await manager.get_run(created.run_id)
    assert paused.current_iteration == 1
    elapsed_before = manager.active_elapsed(created.run_id)
    await asyncio.sleep(0.05)
    assert manager.active_elapsed(created.run_id) - elapsed_before < 0.02

    await manager.resume_run(
        created.run_id,
        ResumeRunRequest(user_override="Add explicit refund reconciliation."),
    )
    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert result.versions[1].revision_plan is not None
    assert (
        result.versions[1].revision_plan.user_override
        == "Add explicit refund reconciliation."
    )


async def test_cancel_during_generation_rejects_late_version() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=20,
        generator_delay=0.03,
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a cancellable product workflow.")
    )
    await wait_for_status(manager, created.run_id, {RunStatus.GENERATING})

    await manager.cancel_run(created.run_id)
    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.CANCELLED
    assert result.versions == []
    terminal_sequence = result.latest_event_sequence
    await asyncio.sleep(0.05)
    assert (await manager.get_run(created.run_id)).latest_event_sequence == (
        terminal_sequence
    )


async def test_pause_requested_during_generation_waits_until_aggregation() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=30,
        generator_delay=0.005,
        reviewer_delay=0.01,
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a generation-stage pause product.")
    )
    await wait_for_status(manager, created.run_id, {RunStatus.GENERATING})

    await manager.request_pause(created.run_id)
    await wait_for_status(manager, created.run_id, {RunStatus.PAUSED})
    paused = await manager.get_run(created.run_id)

    assert paused.versions[0].evaluation is not None
    assert paused.pending_revision_plan is None
    await manager.cancel_run(created.run_id)
    await manager.wait_for_completion(created.run_id, wait_seconds=5)


async def test_cancel_during_review_rejects_late_scores_and_usage() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        generator_delay=0.001,
        reviewer_delay=0.1,
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a review-stage cancellation product.")
    )
    await wait_for_status(manager, created.run_id, {RunStatus.REVIEWING})
    tokens_before = (await manager.get_run(created.run_id)).total_tokens

    await manager.cancel_run(created.run_id)
    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.CANCELLED
    assert result.latest_evaluation is None
    assert result.reviews == {}
    assert result.total_tokens == tokens_before


class RetryOnceGenerator(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__(delays_enabled=False)
        self.calls = 0

    async def stream_prd(
        self,
        *,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan,
        baseline_prd: str | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> AsyncIterator[ProviderTextEvent]:
        self.calls += 1
        if self.calls == 1:
            yield ProviderTextEvent(delta="FAILED ATTEMPT", model="mock")
            raise RetryableProviderError("temporary")
        async for event in super().stream_prd(
            user_idea=user_idea,
            target_audience=target_audience,
            user_constraints=user_constraints,
            iteration=iteration,
            revision_plan=revision_plan,
            baseline_prd=baseline_prd,
            output_language=output_language,
        ):
            yield event


async def test_generator_retry_resets_failed_stream_attempt() -> None:
    provider = RetryOnceGenerator()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a retryable product workflow.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)
    events = manager.event_store.replay(created.run_id, 0)

    assert result.status is RunStatus.COMPLETED
    assert "FAILED ATTEMPT" not in result.versions[0].content
    assert RunEventType.PRD_STREAM_RESET in {event.event for event in events}
    assert provider.calls >= 3


class AttemptObservingGenerator(RetryOnceGenerator):
    """Records the persisted streaming state at the start of every attempt."""

    def __init__(self) -> None:
        super().__init__()
        self.manager: RunManager | None = None
        self.observed: list[tuple[str, int]] = []

    async def stream_prd(
        self,
        *,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan,
        baseline_prd: str | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> AsyncIterator[ProviderTextEvent]:
        assert self.manager is not None
        summaries = await self.manager.list_runs(limit=1)
        snapshot = await self.manager.get_run(summaries[0].run_id)
        self.observed.append((snapshot.current_prd, snapshot.current_prd_attempt))
        async for event in super().stream_prd(
            user_idea=user_idea,
            target_audience=target_audience,
            user_constraints=user_constraints,
            iteration=iteration,
            revision_plan=revision_plan,
            baseline_prd=baseline_prd,
            output_language=output_language,
        ):
            yield event


async def test_snapshot_carries_the_attempt_that_owns_the_streaming_buffer() -> None:
    """A reconnecting client must be able to read the in-flight attempt.

    ``prd_delta`` is transient, so ``current_prd`` alone cannot tell a client
    whether the partial text belongs to attempt 1 or to a retry.
    """
    provider = AttemptObservingGenerator()
    manager = make_manager(provider=provider)
    provider.manager = manager
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build an observable retry product workflow.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    # Every attempt starts from an empty buffer tagged with its own attempt
    # number: iteration 1 attempt 1, iteration 1 attempt 2 after the reset,
    # then iteration 2 attempt 1.
    assert provider.observed == [("", 1), ("", 2), ("", 1)]
    # `prd_generated` is a durable boundary, so the finished text keeps the
    # attempt that produced it rather than reverting to 1.
    assert result.current_prd == result.versions[-1].content
    assert result.current_prd_attempt == 1


async def test_stream_reset_persists_the_retry_attempt_before_any_delta() -> None:
    """The reset commit is durable, so the attempt survives without deltas."""
    provider = RetryOnceGenerator()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a durable retry attempt workflow.")
    )

    await manager.wait_for_completion(created.run_id, wait_seconds=5)
    events = manager.event_store.replay(created.run_id, 0)
    resets = [event for event in events if event.event is RunEventType.PRD_STREAM_RESET]

    assert [event.payload["attempt"] for event in resets] == [2]
    assert resets[0].payload["version"] == 1


async def test_generator_timeout_retries_then_fails_boundedly() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=100,
        generator_delay=2,
    )
    manager = make_manager(
        provider=provider,
        settings=make_settings(
            generator_timeout_seconds=1,
            run_timeout_seconds=10,
        ),
    )
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a bounded timeout product.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=4)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "RUN_TIMEOUT"


async def test_total_active_run_timeout_is_enforced() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=20,
        generator_delay=0.03,
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a total-timeout product.")
    )
    await wait_for_status(manager, created.run_id, {RunStatus.GENERATING})
    manager._active_started[created.run_id] -= 11

    result = await manager.wait_for_completion(created.run_id, wait_seconds=3)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "RUN_TIMEOUT"


async def terminal_payload(manager: RunManager, run_id: object) -> dict[str, object]:
    events = manager.event_store.replay(run_id, 0)  # type: ignore[arg-type]
    terminal = next(
        event
        for event in reversed(events)
        if event.event
        in {RunEventType.RUN_COMPLETED, RunEventType.MAX_ITERATIONS_REACHED}
    )
    return terminal.payload


async def test_score_below_threshold_keeps_iterating() -> None:
    manager = make_manager(provider=NoBlockerProvider())
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product whose first version misses the target.",
            quality_threshold=80,
            max_iterations=3,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert result.current_iteration == 2
    payload = await terminal_payload(manager, created.run_id)
    assert payload["threshold_met"] is True
    assert payload["quality_gate_passed"] is True
    assert payload["must_fix_count"] == 0


async def test_threshold_met_with_open_blocker_keeps_iterating() -> None:
    """The score is not the whole gate: one `must_fix` holds a passing run."""
    provider = SeverityProvider(
        {
            1: [FeedbackSeverity.MUST_FIX],
            2: [FeedbackSeverity.SHOULD_FIX, FeedbackSeverity.OPTIONAL],
        }
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product that scores well but blocks on one gap.",
            quality_threshold=70,
            max_iterations=3,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    # v1 scores 71 against a threshold of 70, so the score half passed on the
    # first round; only the blocking finding sent the run to a second version.
    assert result.versions[0].evaluation is not None
    assert result.versions[0].evaluation.overall_score == 71.0
    assert result.status is RunStatus.COMPLETED
    assert result.current_iteration == 2
    payload = await terminal_payload(manager, created.run_id)
    assert payload["quality_gate_passed"] is True
    assert payload["must_fix_count"] == 0
    assert payload["should_fix_count"] == 3
    assert payload["optional_count"] == 3


async def test_threshold_met_with_no_blocker_passes_the_gate_immediately() -> None:
    provider = SeverityProvider(
        {1: [FeedbackSeverity.SHOULD_FIX, FeedbackSeverity.OPTIONAL]}
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product that clears both halves of the gate.",
            quality_threshold=70,
            max_iterations=3,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert result.current_iteration == 1
    payload = await terminal_payload(manager, created.run_id)
    assert payload["quality_gate_passed"] is True
    assert payload["should_fix_count"] == 3
    assert payload["optional_count"] == 3


async def test_exhausted_budget_with_open_blocker_is_terminal_but_not_passed() -> None:
    """A capped run must not claim the quality goal was met."""
    provider = SeverityProvider(dict.fromkeys(range(1, 6), [FeedbackSeverity.MUST_FIX]))
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product that never clears its blocking findings.",
            quality_threshold=70,
            max_iterations=2,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.MAX_ITERATIONS_REACHED
    payload = await terminal_payload(manager, created.run_id)
    # Both facts are reported side by side: the score target was reached, and
    # the gate still did not pass.
    assert payload["threshold_met"] is True
    assert payload["quality_gate_passed"] is False
    assert payload["must_fix_count"] == 3
    assert payload["completed_iterations"] == 2
    assert payload["max_iterations"] == 2


async def test_capped_run_reports_the_final_round_findings_it_actually_has() -> None:
    """Exhausting the budget is a normal ending; it may not blank the findings.

    The counts on the terminal event have to be the ones the final round's three
    reviewers raised -- the same list the Reviewer panel and the trace show. A
    reader who is told 「未达到目标评分」 next to 必须修复 0 · 重要改进 0 · 可选优化
    0, while the trace beneath it lists 21 items, has no way to tell which number
    to believe.
    """
    provider = SeverityProvider(
        dict.fromkeys(
            range(1, 6),
            [FeedbackSeverity.SHOULD_FIX] * 4 + [FeedbackSeverity.OPTIONAL] * 3,
        )
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product that never reaches a very high target.",
            quality_threshold=99,
            max_iterations=2,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.MAX_ITERATIONS_REACHED
    assert result.latest_evaluation is not None
    counts = result.latest_evaluation.severity_counts()
    # Three reviewers x (4 advisory + 3 optional) for the final version.
    assert counts == {"must_fix": 0, "should_fix": 12, "optional": 9}
    payload = await terminal_payload(manager, created.run_id)
    assert payload["threshold_met"] is False
    assert payload["quality_gate_passed"] is False
    assert payload["must_fix_count"] == counts["must_fix"]
    assert payload["should_fix_count"] == counts["should_fix"]
    assert payload["optional_count"] == counts["optional"]
    # The stored version carries the same evaluation, so a client that reopens
    # the run recomputes the same three numbers.
    final = result.versions[-1].evaluation
    assert final is not None
    assert final.severity_counts() == counts
    assert len(final.combined_feedback) == 21


class RegressingProvider(SeverityProvider):
    """v2 scores lower than v1 while staying free of blocking findings."""

    SCORES = {1: 90, 2: 60}

    def __init__(self) -> None:
        super().__init__(dict.fromkeys(range(1, 6), [FeedbackSeverity.SHOULD_FIX]))

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> ProviderStructuredResult:
        result = await super().generate_review(
            role=role,
            prd=prd,
            iteration=iteration,
            output_language=output_language,
        )
        review = RoleReview.model_validate(result.value)
        result.value = review.model_copy(
            update={"score": self.SCORES.get(iteration, 60)}
        ).model_dump(mode="json")
        return result


async def test_score_regression_keeps_the_historical_best_version() -> None:
    manager = make_manager(provider=RegressingProvider())
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product whose second version scores worse.",
            quality_threshold=95,
            max_iterations=2,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.MAX_ITERATIONS_REACHED
    # Scores are recorded exactly as the reviewers gave them; only the pointer
    # to the strongest version is kept.
    assert [
        version.evaluation.overall_score
        for version in result.versions
        if version.evaluation is not None
    ] == [90.0, 60.0]
    assert result.best_version == 1
    assert result.best_score == 90.0
    payload = await terminal_payload(manager, created.run_id)
    assert payload["final_score"] == 60.0
    assert payload["best_version"] == 1
    assert payload["best_score"] == 90.0
