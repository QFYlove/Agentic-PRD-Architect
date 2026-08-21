"""Round 11 tests: per-node timings, failed-attempt accounting, prompt rules.

The real DeepSeek run these cover took 500 seconds and reported 493 input / 1717
output tokens for the generator, which was the *successful v1* call only -- both
failed v2 attempts contributed nothing to the telemetry, so the recorded spend
could not add up to the bill.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.prd_document import PRD_COMPLETION_MARKER
from backend.prompts import (
    COMPOSITION_RULES,
    GENERATOR_SYSTEM_PROMPT,
    OPTIMIZER_SYSTEM_PROMPT,
)
from backend.providers.base import ProviderTextEvent
from backend.providers.mock import MockLLMProvider
from backend.schemas import (
    CreateRunRequest,
    RevisionPlan,
    RunStatus,
    TokenUsage,
)
from backend.tests.helpers import make_manager

from backend.language import DEFAULT_OUTPUT_LANGUAGE


async def test_every_node_call_records_its_own_duration() -> None:
    """"Which node is slow" is only answerable if the calls stay separate."""
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product whose timings are recorded.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)
    nodes = [timing.node for timing in result.node_timings]

    assert result.status is RunStatus.COMPLETED
    # One generator and three reviewers per version; an optimizer for every
    # version except the last, which is never revised.
    versions = len(result.versions)
    assert nodes.count("generator") == versions
    for reviewer in ("tech_reviewer", "ux_reviewer", "biz_reviewer"):
        assert nodes.count(reviewer) == versions
    assert nodes.count("optimizer") == versions - 1
    assert all(timing.seconds >= 0 for timing in result.node_timings)
    assert all(timing.succeeded for timing in result.node_timings)
    # Each entry names the version it was working on, so "is it getting slower
    # each round" is answerable too.
    generator_versions = [
        timing.version for timing in result.node_timings if timing.node == "generator"
    ]
    assert generator_versions == list(range(1, versions + 1))


async def test_recorded_time_never_exceeds_the_run_wall_clock() -> None:
    """Three reviewers run in parallel, so the sum can exceed elapsed -- but no
    single call can take longer than the run it happened inside."""
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product with plausible timings.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.node_timings
    for timing in result.node_timings:
        assert timing.seconds <= result.elapsed_seconds + 0.5


class TruncatedThenCompleteProvider(MockLLMProvider):
    """The RPG run's shape: attempt 1 is cut off at the cap, attempt 2 works."""

    def __init__(self) -> None:
        super().__init__(delays_enabled=False)
        self.attempts = 0

    async def stream_prd(
        self,
        *,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan: RevisionPlan | None,
        baseline_prd: str | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> AsyncIterator[ProviderTextEvent]:
        self.attempts += 1
        if self.attempts == 1:
            yield ProviderTextEvent(delta="# PRD\n\n## Scope\nCut", model="m")
            yield ProviderTextEvent(
                model="m",
                finish_reason="length",
                usage=TokenUsage(
                    input_tokens=500,
                    output_tokens=1700,
                    total_tokens=2200,
                ),
            )
            return
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


async def test_a_failed_attempt_reports_its_time_and_its_tokens() -> None:
    """The bug behind the RPG run's numbers: a truncated attempt was billed by
    the provider and then dropped from telemetry entirely."""
    provider = TruncatedThenCompleteProvider()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product whose first attempt truncates.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)
    generator = [t for t in result.node_timings if t.node == "generator"]
    failed = [t for t in generator if not t.succeeded]

    assert result.status is RunStatus.COMPLETED
    assert len(failed) == 1
    assert failed[0].attempt == 1
    assert failed[0].output_tokens == 1700
    # And the same tokens reach the totals rather than vanishing.
    assert result.node_tokens["generator"].output_tokens >= 1700
    assert result.total_tokens.output_tokens >= 1700


class NoUsageTruncatingProvider(MockLLMProvider):
    """Truncates without ever reporting usage. Nothing may be invented."""

    async def stream_prd(
        self,
        *,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan: RevisionPlan | None,
        baseline_prd: str | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> AsyncIterator[ProviderTextEvent]:
        del user_idea, target_audience, user_constraints, iteration
        del revision_plan, baseline_prd, output_language
        yield ProviderTextEvent(delta="# PRD\n\n## Scope\nCut", model="m")
        yield ProviderTextEvent(model="m", finish_reason="length")


async def test_an_unreported_spend_stays_zero_rather_than_being_estimated() -> None:
    manager = make_manager(provider=NoUsageTruncatingProvider(delays_enabled=False))
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product with no usage reporting.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)
    generator = [t for t in result.node_timings if t.node == "generator"]

    assert result.status is RunStatus.FAILED
    assert len(generator) == 2
    assert all(not timing.succeeded for timing in generator)
    # A made-up token count is worse than an absent one.
    assert all(timing.output_tokens == 0 for timing in generator)
    assert result.total_tokens.output_tokens == 0


class FailingSecondVersionProvider(MockLLMProvider):
    """v1 generates and is reviewed; every v2 attempt is cut off."""

    async def stream_prd(
        self,
        *,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan: RevisionPlan | None,
        baseline_prd: str | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> AsyncIterator[ProviderTextEvent]:
        if iteration >= 2:
            yield ProviderTextEvent(delta="# PRD\n\n## Scope\nCut", model="m")
            yield ProviderTextEvent(
                model="m",
                finish_reason="length",
                usage=TokenUsage(
                    input_tokens=800,
                    output_tokens=1200,
                    total_tokens=2000,
                ),
            )
            return
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


async def test_a_failed_v2_leaves_v1_its_reviews_and_its_plan_intact() -> None:
    """A run that dies on v2 must not read as "everything is gone"."""
    manager = make_manager(provider=FailingSecondVersionProvider(delays_enabled=False))
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product whose second version fails to generate.",
            quality_threshold=99,
            max_iterations=3,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "PROVIDER_OUTPUT_TRUNCATED"
    # Everything v1 produced survives the failure.
    assert len(result.versions) == 1
    assert result.versions[0].version == 1
    assert result.versions[0].evaluation is not None
    assert PRD_COMPLETION_MARKER not in result.versions[0].content
    assert result.best_version == 1
    assert result.best_score is not None
    # The plan that was going to produce v2 is still readable.
    assert result.pending_revision_plan is not None
    # The failure is attributed to the version that never landed.
    assert result.current_iteration == 2


@pytest.mark.parametrize(
    "prompt", [GENERATOR_SYSTEM_PROMPT, OPTIMIZER_SYSTEM_PROMPT]
)
def test_no_prompt_leaks_provider_or_process_detail(prompt: str) -> None:
    assert "api_key" not in prompt.lower()
    assert "traceback" not in prompt.lower()


def test_the_generator_is_told_to_write_a_document_not_a_checklist() -> None:
    assert COMPOSITION_RULES in GENERATOR_SYSTEM_PROMPT
    # Prose where reasoning lives, tables where dimensions live.
    assert "Prose by default" in COMPOSITION_RULES
    assert "GFM tables" in COMPOSITION_RULES
    assert "| 功能 | 描述 | 优先级 | 验收标准 |" in COMPOSITION_RULES
    # The five allowed diagram types, and only those five.
    for diagram in (
        "flowchart",
        "sequenceDiagram",
        "stateDiagram-v2",
        "mindmap",
        "erDiagram",
    ):
        assert diagram in COMPOSITION_RULES
    for forbidden in ("gantt", "pie", "gitGraph", "quadrantChart"):
        assert forbidden not in COMPOSITION_RULES


def test_the_optimizer_may_not_ask_for_form_only_rewrites() -> None:
    """Otherwise round two turns v1's paragraphs back into bullet lists."""
    lowered = OPTIMIZER_SYSTEM_PROMPT.lower()
    assert "bullet lists" in lowered
    assert "flattened into prose" in lowered
    assert "restructured for clarity" in lowered
