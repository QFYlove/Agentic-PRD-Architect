from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from backend.errors import RetryableProviderError
from backend.providers.base import ProviderTextEvent
from backend.providers.mock import MockLLMProvider
from backend.schemas import (
    CreateRunRequest,
    ResumeRunRequest,
    ReviewRole,
    RunEventType,
    RunStatus,
)
from backend.tests.helpers import make_manager, make_settings


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
    manager = make_manager()
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
    ):
        self.started.add(role)
        if len(self.started) == 3:
            self.all_started.set()
        await asyncio.wait_for(self.all_started.wait(), timeout=1)
        return await super().generate_review(
            role=role,
            prd=prd,
            iteration=iteration,
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
