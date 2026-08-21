from __future__ import annotations

from backend.prompts import (
    BUSINESS_REVIEWER_SYSTEM_PROMPT,
    GENERATOR_SYSTEM_PROMPT,
    OPTIMIZER_SYSTEM_PROMPT,
    SEVERITY_RUBRIC,
    TECH_REVIEWER_SYSTEM_PROMPT,
    UX_REVIEWER_SYSTEM_PROMPT,
)
from backend.providers.mock import MockLLMProvider
from backend.schemas import (
    EvaluationResult,
    FeedbackItem,
    FeedbackSeverity,
    ReviewRole,
    RevisionPlan,
    RevisionPriority,
    RoleReview,
)


async def collect_prd(provider: MockLLMProvider, iteration: int) -> str:
    chunks: list[str] = []
    async for event in provider.stream_prd(
        user_idea="Build a podcast micro-subscription product.",
        target_audience="Listeners and creators",
        user_constraints="Mobile-first MVP",
        iteration=iteration,
        revision_plan=None,
    ):
        chunks.append(event.delta)
    return "".join(chunks)


async def test_mock_generator_supports_all_iterations_deterministically() -> None:
    provider = MockLLMProvider(delays_enabled=False)

    first = [await collect_prd(provider, iteration) for iteration in range(1, 6)]
    second = [await collect_prd(provider, iteration) for iteration in range(1, 6)]

    assert first == second
    assert len(set(first)) == 5
    assert "Gateway Error & Retry Fallbacks" in first[1]


async def test_mock_reviewers_match_demo_scores_and_never_decline() -> None:
    provider = MockLLMProvider(delays_enabled=False)
    expected = {
        ReviewRole.TECH: (65, 88),
        ReviewRole.UX: (70, 89),
        ReviewRole.BIZ: (78, 87),
    }

    for role in ReviewRole:
        scores: list[int] = []
        for iteration in range(1, 6):
            result = await provider.generate_review(
                role=role,
                prd="# PRD",
                iteration=iteration,
            )
            review = RoleReview.model_validate(result.value)
            scores.append(review.score)
        assert tuple(scores[:2]) == expected[role]
        assert scores == sorted(scores)


async def test_mock_optimizer_preserves_roles_and_user_override() -> None:
    provider = MockLLMProvider(delays_enabled=False)
    reviews = {}
    for role in ReviewRole:
        result = await provider.generate_review(role=role, prd="# PRD", iteration=1)
        reviews[role] = RoleReview.model_validate(result.value)
    evaluation = EvaluationResult(
        tech=reviews[ReviewRole.TECH],
        ux=reviews[ReviewRole.UX],
        biz=reviews[ReviewRole.BIZ],
        overall_score=71.0,
    )

    result = await provider.generate_revision_plan(
        evaluation=evaluation,
        iteration=1,
        user_override="Add payout reconciliation.",
    )
    plan = RevisionPlan.model_validate(result.value)

    assert {item.source_role.value for item in plan.items} == {
        "tech",
        "ux",
        "biz",
        "user",
    }
    assert plan.user_override == "Add payout reconciliation."


async def test_mock_optimizer_merges_duplicate_feedback_and_keeps_sources() -> None:
    provider = MockLLMProvider(delays_enabled=False)
    shared = "Add an explicit recovery path."
    reviews = {
        role: RoleReview(
            role=role,
            score=70,
            summary="Review",
            feedback=[
                FeedbackItem(
                    severity=FeedbackSeverity.MUST_FIX,
                    issue=shared,
                    recommendation="Document the recovery path.",
                )
            ],
        )
        for role in ReviewRole
    }
    evaluation = EvaluationResult(
        tech=reviews[ReviewRole.TECH],
        ux=reviews[ReviewRole.UX],
        biz=reviews[ReviewRole.BIZ],
        overall_score=70,
    )

    result = await provider.generate_revision_plan(
        evaluation=evaluation,
        iteration=1,
        user_override=None,
    )
    plan = RevisionPlan.model_validate(result.value)

    assert len(plan.items) == 1
    assert {source.value for source in plan.items[0].source_roles} == {
        "tech",
        "ux",
        "biz",
    }


async def test_mock_reviews_carry_all_three_severities_on_the_first_round() -> None:
    provider = MockLLMProvider(delays_enabled=False)

    for role in ReviewRole:
        result = await provider.generate_review(role=role, prd="# PRD", iteration=1)
        review = RoleReview.model_validate(result.value)

        assert {item.severity for item in review.feedback} == set(FeedbackSeverity)
        assert len(review.feedback_by_severity(FeedbackSeverity.MUST_FIX)) == 1
        for item in review.feedback:
            assert item.issue.strip() != ""
            assert item.recommendation.strip() != ""


async def test_mock_blocking_findings_clear_after_the_first_round() -> None:
    """The second version is the "target met, advice open" state the UI must show."""
    provider = MockLLMProvider(delays_enabled=False)

    for iteration in range(2, 6):
        for role in ReviewRole:
            result = await provider.generate_review(
                role=role,
                prd="# PRD",
                iteration=iteration,
            )
            review = RoleReview.model_validate(result.value)

            assert review.feedback_by_severity(FeedbackSeverity.MUST_FIX) == []
            assert review.feedback_by_severity(FeedbackSeverity.SHOULD_FIX) != []
            assert review.feedback_by_severity(FeedbackSeverity.OPTIONAL) != []


async def test_mock_optimizer_maps_severity_to_priority_and_drops_optional() -> None:
    provider = MockLLMProvider(delays_enabled=False)
    reviews = {
        role: RoleReview(
            role=role,
            score=80,
            summary="Review",
            feedback=[
                FeedbackItem(
                    severity=severity,
                    issue=f"{role.value} {severity.value}",
                    recommendation=f"Fix {role.value} {severity.value}",
                )
                for severity in FeedbackSeverity
            ],
        )
        for role in ReviewRole
    }
    evaluation = EvaluationResult(
        tech=reviews[ReviewRole.TECH],
        ux=reviews[ReviewRole.UX],
        biz=reviews[ReviewRole.BIZ],
        overall_score=80,
    )

    result = await provider.generate_revision_plan(
        evaluation=evaluation,
        iteration=1,
        user_override=None,
    )
    plan = RevisionPlan.model_validate(result.value)

    assert [item.priority for item in plan.items] == [
        RevisionPriority.HIGH,
        RevisionPriority.MEDIUM,
    ] * 3
    assert all("optional" not in item.issue for item in plan.items)
    # The plan carries the recommendation, not a restatement of the issue.
    assert plan.items[0].required_change.startswith("Fix ")


def test_prompts_keep_roles_and_user_data_boundaries_independent() -> None:
    prompts = [
        GENERATOR_SYSTEM_PROMPT,
        TECH_REVIEWER_SYSTEM_PROMPT,
        UX_REVIEWER_SYSTEM_PROMPT,
        BUSINESS_REVIEWER_SYSTEM_PROMPT,
        OPTIMIZER_SYSTEM_PROMPT,
    ]

    assert len(set(prompts)) == 5
    for prompt in prompts:
        assert "<user_input>" in prompt
        assert "hidden reasoning" in prompt


def test_every_reviewer_prompt_carries_the_severity_rubric() -> None:
    """Without the rubric a model marks every suggestion `must_fix`, which turns
    the quality gate into "iterate until the budget runs out"."""
    for prompt in (
        TECH_REVIEWER_SYSTEM_PROMPT,
        UX_REVIEWER_SYSTEM_PROMPT,
        BUSINESS_REVIEWER_SYSTEM_PROMPT,
    ):
        assert SEVERITY_RUBRIC in prompt


def test_severity_rubric_names_every_tier_and_bounds_must_fix() -> None:
    for severity in FeedbackSeverity:
        assert f"`{severity.value}`" in SEVERITY_RUBRIC
    # The escalation criteria and the explicit non-blockers both have to be
    # present: the negative list is what stops score-target inflation.
    for criterion in (
        "core business flow is not executable",
        "security, compliance, privacy",
        "contradict each other",
        "acceptance criteria",
        "major business risk",
    ):
        assert criterion in SEVERITY_RUBRIC
    for non_blocker in (
        "quantified further",
        "more specific",
        "onboarding",
        "edge-state",
        "business modelling",
        "UX polish",
    ):
        assert non_blocker in SEVERITY_RUBRIC
    assert "zero `must_fix`" in SEVERITY_RUBRIC


def test_optimizer_prompt_maps_severity_onto_priority() -> None:
    for mapping in (
        "`must_fix` -> high",
        "`should_fix` ->\nmedium",
        "`optional` -> low",
    ):
        assert mapping in OPTIMIZER_SYSTEM_PROMPT
