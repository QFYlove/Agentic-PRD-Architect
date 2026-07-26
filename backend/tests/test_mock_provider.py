from __future__ import annotations

from backend.prompts import (
    BUSINESS_REVIEWER_SYSTEM_PROMPT,
    GENERATOR_SYSTEM_PROMPT,
    OPTIMIZER_SYSTEM_PROMPT,
    TECH_REVIEWER_SYSTEM_PROMPT,
    UX_REVIEWER_SYSTEM_PROMPT,
)
from backend.providers.mock import MockLLMProvider
from backend.schemas import (
    EvaluationResult,
    ReviewRole,
    RevisionPlan,
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
            feedback=[shared],
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
