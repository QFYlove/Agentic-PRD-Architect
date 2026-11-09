"""Round 11 tests: per-node timings, failed-attempt accounting, prompt rules.

The real DeepSeek run these cover took 500 seconds and reported 493 input / 1717
output tokens for the generator, which was the *successful v1* call only -- both
failed v2 attempts contributed nothing to the telemetry, so the recorded spend
could not add up to the bill.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.language import DEFAULT_OUTPUT_LANGUAGE
from backend.prd_document import PRD_COMPLETION_MARKER
from backend.prd_quality import check_prd
from backend.prompts import (
    COMPACT_GENERATOR_SYSTEM_PROMPT,
    FACT_RULES,
    GENERATOR_SYSTEM_PROMPT,
    OPTIMIZER_SYSTEM_PROMPT,
    STRUCTURE_RULES,
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


async def test_every_node_call_records_its_own_duration() -> None:
    """ "Which node is slow" is only answerable if the calls stay separate."""
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
    """Attempt 1 is broken off by the service after being billed; attempt 2 works.

    The RPG run's attempt 1 was cut off at the output cap. Cap truncations are no
    longer retried (they cannot succeed unchanged), so the retried case here is a
    service interruption -- the accounting question is identical.
    """

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
                finish_reason="insufficient_system_resource",
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
    # One attempt: a cap truncation is never re-sent unchanged.
    assert len(generator) == 1
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


@pytest.mark.parametrize("prompt", [GENERATOR_SYSTEM_PROMPT, OPTIMIZER_SYSTEM_PROMPT])
def test_no_prompt_leaks_provider_or_process_detail(prompt: str) -> None:
    assert "api_key" not in prompt.lower()
    assert "traceback" not in prompt.lower()


def test_the_generator_is_told_to_structure_rules_as_lists_and_tables() -> None:
    """Replaces the old "Prose by default" contract.

    Run 9fa59292 followed that rule to the letter: zero list lines in either
    version, and 17 paragraphs over 300 characters by v2. The new rules keep short
    prose for reasoning and put rules, flows and criteria where a reader can scan
    them -- and the deterministic checker enforces the same limit it quotes.
    """
    assert STRUCTURE_RULES in GENERATOR_SYSTEM_PROMPT
    assert "Prose by default" not in GENERATOR_SYSTEM_PROMPT
    for rule in (
        "Bullet lists for features, business rules",
        "Numbered steps for user and system flows",
        "GFM tables for anything with two or more attributes",
        "Never write a paragraph longer than 300",
        "（1）…（2）…（3）…",
        "DEPTH BY PRIORITY",
        "P2: future value and direction only",
        "8. 假设与待确认事项",
    ):
        assert rule in STRUCTURE_RULES
    # The five allowed diagram types, and only those five.
    for diagram in (
        "flowchart",
        "sequenceDiagram",
        "stateDiagram-v2",
        "mindmap",
        "erDiagram",
    ):
        assert diagram in STRUCTURE_RULES
    for forbidden in ("gantt", "pie", "gitGraph", "quadrantChart"):
        assert forbidden not in STRUCTURE_RULES


def test_the_generator_has_a_length_budget_and_a_compact_mode() -> None:
    assert "LENGTH BUDGET" in GENERATOR_SYSTEM_PROMPT
    assert "12,000-18,000" in GENERATOR_SYSTEM_PROMPT
    assert "compact mode" in COMPACT_GENERATOR_SYSTEM_PROMPT
    assert "7,000-11,000" in COMPACT_GENERATOR_SYSTEM_PROMPT
    # A revision must be able to shrink the document.
    for change in ("REMOVE", "CONSOLIDATE", "RETAIN", "affected_sections"):
        assert change in GENERATOR_SYSTEM_PROMPT


def test_the_generator_must_label_figures_and_never_invent_sources() -> None:
    assert FACT_RULES in GENERATOR_SYSTEM_PROMPT
    for label in ("[用户输入]", "[已验证事实]", "[假设]", "[建议]", "[待确认]"):
        assert label in FACT_RULES
    assert "内部试点" in FACT_RULES
    assert (
        "| 事项 | 类型 | 为什么需要 | 影响的决策 | 验证方式 | 阶段/负责人 |"
        in FACT_RULES
    )


def test_a_wall_of_text_document_is_flagged_by_the_same_rules() -> None:
    """The prompt and the checker agree on what a wall of text is."""
    wall = "这是一段很长的说明文字，" * 40
    report = check_prd(f"# PRD\n\n## 1. 产品概述\n{wall}\n")

    assert report.long_paragraphs == 1
    assert report.list_items == 0
    assert any(issue.code == "long_paragraph" for issue in report.issues)


def test_the_optimizer_may_not_ask_for_form_only_rewrites() -> None:
    """A plan item changes content; it never reshapes a section for its own sake."""
    lowered = OPTIMIZER_SYSTEM_PROMPT.lower()
    assert "paragraphs become bullets" in lowered
    assert "tables become prose" in lowered
    assert "rewrite of the whole document" in lowered
