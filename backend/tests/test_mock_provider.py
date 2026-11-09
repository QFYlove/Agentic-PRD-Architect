from __future__ import annotations

from backend.prompts import (
    BUSINESS_REVIEWER_SYSTEM_PROMPT,
    COMPACT_GENERATOR_SYSTEM_PROMPT,
    FACT_RULES,
    FINDING_RULES,
    GENERATOR_SYSTEM_PROMPT,
    OPTIMIZER_SYSTEM_PROMPT,
    SEVERITY_RUBRIC,
    STRUCTURE_RULES,
    TECH_REVIEWER_SYSTEM_PROMPT,
    UX_REVIEWER_SYSTEM_PROMPT,
)
from backend.providers.base import OptimizerContext, UserRequirements
from backend.providers.mock import MockLLMProvider
from backend.rubric import ROLE_RUBRICS
from backend.schemas import (
    ChangeType,
    FeedbackSeverity,
    OptimizerOutput,
    ReviewerOutput,
    ReviewRole,
)
from backend.scoring import build_evaluation, normalize_review
from backend.tests.helpers import role_review

REVIEWER_PROMPTS = (
    TECH_REVIEWER_SYSTEM_PROMPT,
    UX_REVIEWER_SYSTEM_PROMPT,
    BUSINESS_REVIEWER_SYSTEM_PROMPT,
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


async def reviews_for(
    provider: MockLLMProvider, iteration: int
) -> dict[ReviewRole, ReviewerOutput]:
    reviews = {}
    for role in ReviewRole:
        result = await provider.generate_review(
            role=role, prd="# PRD", iteration=iteration
        )
        reviews[role] = ReviewerOutput.model_validate(result.value)
    return reviews


async def test_mock_generator_supports_all_iterations_deterministically() -> None:
    provider = MockLLMProvider(delays_enabled=False)

    first = [await collect_prd(provider, iteration) for iteration in range(1, 6)]
    second = [await collect_prd(provider, iteration) for iteration in range(1, 6)]

    assert first == second
    assert len(set(first)) == 5
    assert "Payment Failure and Refunds" in first[1]


async def test_mock_reviewers_never_send_a_total_score() -> None:
    """The model-facing contract has no `score`: the backend computes it."""
    provider = MockLLMProvider(delays_enabled=False)

    for role, output in (await reviews_for(provider, 1)).items():
        assert "score" not in output.model_dump()
        assert [item.dimension for item in output.dimension_scores] == [
            dimension.id for dimension in ROLE_RUBRICS[role.value]
        ]


async def test_mock_reviewers_reach_the_demo_scores_through_the_rubric() -> None:
    provider = MockLLMProvider(delays_enabled=False)
    expected = {
        ReviewRole.TECH: (65, 88),
        ReviewRole.UX: (70, 89),
        ReviewRole.BIZ: (78, 87),
    }

    for role in ReviewRole:
        scores = []
        for iteration in range(1, 6):
            output = (await reviews_for(provider, iteration))[role]
            scores.append(normalize_review(output, version=iteration).score)
        assert tuple(scores[:2]) == expected[role]
        assert scores == sorted(scores)


async def test_mock_reviews_carry_all_three_severities_on_the_first_round() -> None:
    provider = MockLLMProvider(delays_enabled=False)

    for output in (await reviews_for(provider, 1)).values():
        assert {item.severity for item in output.findings} == set(FeedbackSeverity)
        for item in output.findings:
            assert item.evidence.strip() != ""
            assert item.section.strip() != ""
            assert item.recommendation.strip() != ""


async def test_mock_blocking_findings_clear_after_the_first_round() -> None:
    """The second version is the "target met, advice open" state the UI must show."""
    provider = MockLLMProvider(delays_enabled=False)

    for iteration in range(2, 6):
        for output in (await reviews_for(provider, iteration)).values():
            severities = {item.severity for item in output.findings}
            assert FeedbackSeverity.MUST_FIX not in severities
            assert FeedbackSeverity.SHOULD_FIX in severities


async def test_tech_and_ux_payment_findings_are_merged_by_the_aggregator() -> None:
    """The mock deliberately raises one problem from two roles."""
    provider = MockLLMProvider(delays_enabled=False)
    outputs = await reviews_for(provider, 1)
    reviews = {
        role: normalize_review(output, version=1) for role, output in outputs.items()
    }

    evaluation, gate = build_evaluation(
        reviews[ReviewRole.TECH],
        reviews[ReviewRole.UX],
        reviews[ReviewRole.BIZ],
        quality_threshold=85,
    )

    merged = [item for item in evaluation.combined_feedback if item.merged_from]
    assert len(merged) == 1
    assert merged[0].source_roles == [ReviewRole.TECH, ReviewRole.UX]
    assert {observation.role for observation in merged[0].observations} == {
        ReviewRole.TECH,
        ReviewRole.UX,
    }
    assert evaluation.findings_before_dedup == len(evaluation.combined_feedback) + 1
    assert gate.must_fix_count == 2


async def test_mock_optimizer_cites_finding_ids_and_declines_optional() -> None:
    provider = MockLLMProvider(delays_enabled=False)
    evaluation, _ = build_evaluation(
        role_review(ReviewRole.TECH, score=70),
        role_review(ReviewRole.UX, score=70),
        role_review(ReviewRole.BIZ, score=70),
        quality_threshold=85,
    )
    outputs = await reviews_for(provider, 1)
    evaluation, _ = build_evaluation(
        *(normalize_review(outputs[role], version=1) for role in ReviewRole),
        quality_threshold=85,
    )

    result = await provider.generate_revision_plan(
        evaluation=evaluation,
        iteration=1,
        user_override="Add payout reconciliation.",
        context=OptimizerContext(
            requirements=UserRequirements(user_idea="Build a podcast product."),
            prd="# PRD",
            reviewed_version=1,
            baseline_version=1,
        ),
    )
    output = OptimizerOutput.model_validate(result.value)

    known = {item.finding_id for item in evaluation.combined_feedback}
    for item in output.items:
        assert set(item.source_finding_ids) - {"user"} <= known | {
            merged
            for finding in evaluation.combined_feedback
            for merged in finding.merged_from
        }
        assert item.change_type in set(ChangeType)
    optional = {
        item.finding_id
        for item in evaluation.combined_feedback
        if item.severity is FeedbackSeverity.OPTIONAL
    }
    assert {item.finding_id for item in output.declined_findings} == optional
    assert any("user" in item.source_finding_ids for item in output.items)


def test_prompts_keep_roles_and_user_data_boundaries_independent() -> None:
    prompts = [GENERATOR_SYSTEM_PROMPT, *REVIEWER_PROMPTS, OPTIMIZER_SYSTEM_PROMPT]

    assert len(set(prompts)) == 5
    for prompt in prompts:
        # The provider wraps every payload in this tag; each prompt names it.
        assert "<user_input_json>" in prompt
        assert "untrusted" in prompt
        assert "hidden reasoning" in prompt


def test_every_reviewer_prompt_carries_the_shared_rules_and_its_own_rubric() -> None:
    for role, prompt in zip(("tech", "ux", "biz"), REVIEWER_PROMPTS, strict=True):
        assert SEVERITY_RUBRIC in prompt
        assert FINDING_RULES in prompt
        for dimension in ROLE_RUBRICS[role]:
            assert f"`{dimension.id}`" in prompt
            assert f"weight {round(dimension.weight * 100)}%" in prompt
        assert "user_requirements" in prompt
        # A reviewer never produces the total.
        assert "You do not produce a total score" in prompt


def test_severity_rubric_names_every_tier_and_bounds_must_fix() -> None:
    for tier in ("`must_fix`", "`should_fix`", "`optional`"):
        assert tier in SEVERITY_RUBRIC
    for criterion in (
        "core user need",
        "contradict each other",
        "hard constraint",
        "security, privacy, compliance",
        "cannot be built",
    ):
        assert criterion in SEVERITY_RUBRIC
    # Missing data is advice, never a blocker, and never a request to invent.
    assert "Missing data is not a defect" in SEVERITY_RUBRIC
    assert "Never ask the document to invent a number" in SEVERITY_RUBRIC


def test_finding_rules_require_evidence_allow_empty_and_cap_the_list() -> None:
    assert "`evidence`" in FINDING_RULES
    assert "`user_impact`" in FINDING_RULES
    assert "at most 5 findings" in FINDING_RULES
    assert "Zero is a correct answer" in FINDING_RULES
    assert "at most two sentences" in FINDING_RULES
    assert "at most\nthree" in FINDING_RULES


def test_optimizer_prompt_reads_the_document_and_can_shrink_it() -> None:
    for required in (
        "`prd`",
        "`affected_sections`",
        "UPDATE / REMOVE / CONSOLIDATE over ADD",
        "RETAIN",
        "`must_preserve`",
        "`source_finding_ids`",
        "`declined_findings`",
        'never plan "add a value"',
        "`must_fix` -> high",
        "`should_fix` -> medium",
    ):
        assert required in OPTIMIZER_SYSTEM_PROMPT


def test_compact_generator_prompt_differs_only_in_its_budget() -> None:
    assert COMPACT_GENERATOR_SYSTEM_PROMPT != GENERATOR_SYSTEM_PROMPT
    assert "compact mode" in COMPACT_GENERATOR_SYSTEM_PROMPT
    assert STRUCTURE_RULES in COMPACT_GENERATOR_SYSTEM_PROMPT
    assert FACT_RULES in COMPACT_GENERATOR_SYSTEM_PROMPT
