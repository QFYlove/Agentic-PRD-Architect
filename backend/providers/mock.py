from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from functools import lru_cache
from itertools import product
from typing import Any

from backend.language import DEFAULT_OUTPUT_LANGUAGE
from backend.prd_document import PRD_COMPLETION_MARKER
from backend.providers.base import (
    LLMProvider,
    OptimizerContext,
    ProviderStructuredResult,
    ProviderTextEvent,
    ReviewContext,
)
from backend.rubric import DIMENSION_SCORE_MAX, DIMENSION_SCORE_MIN, dimensions_for
from backend.schemas import (
    ChangeType,
    DeclinedFinding,
    DimensionScoreInput,
    EvaluationResult,
    FeedbackSeverity,
    FindingCategory,
    FindingInput,
    FindingStatus,
    GenerationMode,
    OptimizerOutput,
    ResolutionInput,
    ReviewerOutput,
    ReviewRole,
    RevisionItemInput,
    RevisionPlan,
    RevisionPriority,
    TokenUsage,
)

#: Role scores the mock aims for per iteration. The backend computes the actual
#: score from dimension scores, so these are reached by choosing dimensions.
SCORES: dict[ReviewRole, tuple[int, ...]] = {
    ReviewRole.TECH: (65, 88, 90, 92, 94),
    ReviewRole.UX: (70, 89, 91, 93, 95),
    ReviewRole.BIZ: (78, 87, 89, 91, 93),
}


@lru_cache(maxsize=256)
def _dimension_combo(role: str, target: int) -> tuple[int, ...]:
    """The 1-5 dimension scores whose weighted score is closest to ``target``.

    Ties prefer the most even spread, so a mock review reads like a real one
    rather than a 1 next to a 5.
    """
    dimensions = dimensions_for(role)
    best: tuple[float, float, tuple[int, ...]] | None = None
    for combo in product(
        range(DIMENSION_SCORE_MIN, DIMENSION_SCORE_MAX + 1), repeat=len(dimensions)
    ):
        score = sum(
            value / DIMENSION_SCORE_MAX * dimension.weight * 100
            for value, dimension in zip(combo, dimensions, strict=True)
        )
        spread = max(combo) - min(combo)
        key = (abs(round(score) - target), spread, combo)
        if best is None or key < best:
            best = key
    assert best is not None
    return best[2]


def dimension_scores_for(role: ReviewRole, target: int) -> list[DimensionScoreInput]:
    combo = _dimension_combo(role.value, target)
    return [
        DimensionScoreInput(
            dimension=dimension.id,
            score=value,
            rationale=f"{dimension.label_en}: rated {value}/5 against the anchors.",
        )
        for value, dimension in zip(combo, dimensions_for(role.value), strict=True)
    ]


def _finding(
    title: str,
    severity: FeedbackSeverity,
    category: FindingCategory,
    section: str,
    evidence: str,
    problem: str,
    impact: str,
    recommendation: str,
) -> FindingInput:
    return FindingInput(
        title=title,
        severity=severity,
        category=category,
        section=section,
        evidence=evidence,
        problem=problem,
        user_impact=impact,
        recommendation=recommendation,
        confidence=0.9,
    )


#: Findings a first draft genuinely blocks on. Tech and UX describe the same gap
#: from two sides -- the aggregator is expected to merge them into one.
BLOCKING_FINDINGS: dict[ReviewRole, FindingInput] = {
    ReviewRole.TECH: _finding(
        "Payment failure handling is undefined",
        FeedbackSeverity.MUST_FIX,
        FindingCategory.MISSING_FLOW,
        "5.1 Purchase Flow",
        "5.1 lists the purchase steps but never says what happens when the "
        "gateway call fails.",
        "Gateway failures have no defined handling, so the purchase flow cannot "
        "be built.",
        "Engineers must guess retry and failure behaviour for money movement.",
        "Specify idempotent retries, timeout behaviour, and a terminal failure "
        "state for every gateway call.",
    ),
    ReviewRole.UX: _finding(
        "Payment failure state is undefined",
        FeedbackSeverity.MUST_FIX,
        FindingCategory.STATE_FEEDBACK,
        "5.1 Purchase Flow",
        "5.1 has no screen or message for a failed purchase.",
        "A failed purchase leaves the listener with no visible state, so the "
        "core journey dead-ends.",
        "Listeners cannot tell whether they were charged or what to do next.",
        "Define the failure screen, its retry affordance, and an accessible "
        "error announcement.",
    ),
    ReviewRole.BIZ: _finding(
        "Refund policy is missing",
        FeedbackSeverity.MUST_FIX,
        FindingCategory.BUSINESS_VALUE,
        "7. Metrics and Business Rules",
        "Chapter 7 defines purchases but no refund rule.",
        "Refunds move money with no stated policy, which is an unmanaged "
        "financial and compliance risk.",
        "Support and finance cannot settle disputes consistently.",
        "Define refund eligibility, who approves it, and how a refund settles "
        "against the creator payout.",
    ),
}

#: Real gaps that do not stop the document from shipping.
IMPROVEMENT_FINDINGS: dict[ReviewRole, FindingInput] = {
    ReviewRole.TECH: _finding(
        "Fraud protection is qualitative",
        FeedbackSeverity.SHOULD_FIX,
        FindingCategory.TECHNICAL_RISK,
        "6. Non-Functional Requirements",
        "Chapter 6 mentions fraud only as a goal.",
        "Fraud protection is described qualitatively.",
        "Abuse cannot be detected or capped at launch.",
        "Add velocity limits, audit events, and a manual review queue.",
    ),
    ReviewRole.UX: _finding(
        "Offline recovery per screen",
        FeedbackSeverity.SHOULD_FIX,
        FindingCategory.EDGE_CASE,
        "4. Core Flow",
        "Chapter 4 says offline is handled but not on which screen.",
        "Offline recovery is mentioned but not specified per screen.",
        "Listeners on weak networks lose their place in the flow.",
        "Describe what each purchase screen shows once connectivity drops.",
    ),
    ReviewRole.BIZ: _finding(
        "Guardrail metrics have no owner",
        FeedbackSeverity.SHOULD_FIX,
        FindingCategory.SCOPE_PRIORITY,
        "7. Metrics and Business Rules",
        "The metrics table lists names without owners.",
        "Guardrail metrics have no owner or alert condition.",
        "Regressions after launch go unnoticed.",
        "Give dispute rate, churn, and fraud rate an owner and an alert "
        "condition; mark any threshold as [待确认].",
    ),
}

#: Polish. Present so the UI has a third tier to render, never a blocker.
OPTIONAL_FINDINGS: dict[ReviewRole, tuple[FindingInput, ...]] = {
    ReviewRole.TECH: (
        _finding(
            "Log retention unspecified",
            FeedbackSeverity.OPTIONAL,
            FindingCategory.TECHNICAL_RISK,
            "6. Non-Functional Requirements",
            "Chapter 6 mentions structured logs without retention.",
            "Log retention is unspecified.",
            "Storage and privacy review cannot size logs.",
            "State a retention window for structured purchase logs.",
        ),
        _finding(
            "Catalogue cache strategy",
            FeedbackSeverity.OPTIONAL,
            FindingCategory.TECHNICAL_RISK,
            "5.1 Purchase Flow",
            "5.1 loads the creator catalogue on every visit.",
            "The client cache strategy could be more concrete.",
            "Slightly slower catalogue loads.",
            "Name the cache layer used for the creator catalogue.",
        ),
    ),
    ReviewRole.UX: (
        _finding(
            "First-run explanation",
            FeedbackSeverity.OPTIONAL,
            FindingCategory.UX_CLARITY,
            "2. Users and Scenarios",
            "Scenario 1 starts at the purchase button.",
            "First-run onboarding could be warmer.",
            "New listeners may not understand single-episode purchases.",
            "Add a one-screen explanation of what a single-episode purchase is.",
        ),
        _finding(
            "Receipt wording",
            FeedbackSeverity.OPTIONAL,
            FindingCategory.UX_CLARITY,
            "5.1 Purchase Flow",
            "The receipt step uses billing terms.",
            "Receipt wording could be friendlier.",
            "Minor confusion on the receipt screen.",
            "Reword the receipt copy in the listener's own terms.",
        ),
    ),
    ReviewRole.BIZ: (
        _finding(
            "Price sensitivity not explored",
            FeedbackSeverity.OPTIONAL,
            FindingCategory.QUANTIFICATION,
            "7. Metrics and Business Rules",
            "Chapter 7 names one price point marked [假设].",
            "Pricing sensitivity is not explored.",
            "The launch price may be suboptimal.",
            "List two candidate price points as [假设] to test after launch.",
        ),
        _finding(
            "Creator reporting depth",
            FeedbackSeverity.OPTIONAL,
            FindingCategory.BUSINESS_VALUE,
            "3. Scope and Features",
            "The P1 row for creator reporting is one line.",
            "Creator-side reporting could go deeper.",
            "Creators see less detail than they may want.",
            "Add a per-episode revenue breakdown to the creator dashboard (P1).",
        ),
    ),
}


def mock_findings(role: ReviewRole, iteration: int) -> list[FindingInput]:
    """Three tiers per reviewer, with the blockers cleared after the first pass."""
    items: list[FindingInput] = []
    if iteration <= 1:
        items.append(BLOCKING_FINDINGS[role])
    items.append(IMPROVEMENT_FINDINGS[role])
    items.extend(OPTIONAL_FINDINGS[role])
    return items


def mock_review_output(
    role: ReviewRole,
    *,
    score: int,
    findings: list[FindingInput],
    summary: str | None = None,
    resolutions: list[ResolutionInput] | None = None,
) -> dict[str, Any]:
    """A valid ``ReviewerOutput`` value whose computed score is ``score``."""
    return ReviewerOutput(
        role=role,
        summary=summary or f"{role.value.title()} review.",
        strengths=["Clear scope", "Measurable acceptance criteria"],
        dimension_scores=dimension_scores_for(role, score),
        findings=findings,
        resolutions=resolutions or [],
    ).model_dump(mode="json")


_PRIORITY = {
    FeedbackSeverity.MUST_FIX: RevisionPriority.HIGH,
    FeedbackSeverity.SHOULD_FIX: RevisionPriority.MEDIUM,
    FeedbackSeverity.OPTIONAL: RevisionPriority.LOW,
}


class MockLLMProvider(LLMProvider):
    is_mock = True

    def __init__(
        self,
        *,
        delays_enabled: bool = True,
        chunk_size: int = 72,
        generator_delay: float = 0.01,
        reviewer_delay: float = 0.02,
        optimizer_delay: float = 0.02,
    ) -> None:
        self.delays_enabled = delays_enabled
        self.chunk_size = chunk_size
        self.generator_delay = generator_delay
        self.reviewer_delay = reviewer_delay
        self.optimizer_delay = optimizer_delay

    async def _sleep(self, delay: float) -> None:
        if self.delays_enabled and delay > 0:
            await asyncio.sleep(delay)

    def _prd(
        self,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan: RevisionPlan | None,
    ) -> str:
        improvements = ""
        if iteration >= 2:
            improvements = """
### 5.2 Payment Failure and Refunds
- Gateway calls use idempotency keys and at most two retries.
- A failed purchase shows a failure screen with retry and support actions.
- Refund requests move through pending, approved, and rejected states.

**Acceptance criteria**
- A gateway timeout never charges twice.
- A refund settles against the creator payout within one payout cycle.
"""
        later = ""
        if iteration >= 3:
            later = """
### 5.3 Operational Readiness
- Incidents have an owner, a severity, and a rollback criterion.
- Support runbooks cover failed purchases and refunds.
"""
        # A revision plan changes the document, never narrates itself: no
        # "Applied revision plan:" scaffolding, and sections the plan did not
        # name come out identical round to round (the stability test asserts
        # that). A user override is a real requirement, so it lands as content.
        requested = ""
        override = revision_plan.user_override if revision_plan else None
        if override:
            requested = f"""
### 5.9 User Requirements
- {override}
"""
        return f"""# Product Requirements Document — Version {iteration}

## 1. Product Overview
{user_idea}

- Problem: listeners cannot pay for a single episode without a subscription.
- Outcome: a trustworthy purchase with explicit success, failure, and
  recovery states.

## 2. Users and Scenarios
| Segment | Need |
|---|---|
| {target_audience or "Product teams and their customers"} | Buy one episode quickly |

## 3. Scope and Features
| Feature | Priority | Acceptance |
|---|---|---|
| Single-episode purchase | P0 | Purchase completes in one flow |
| Creator reporting | P1 | Per-episode totals visible |

## 4. Core Flow
1. The listener opens an episode and chooses to buy it.
2. The listener confirms the price and pays.
3. The episode unlocks and a receipt is shown.

## 5. Detailed Requirements
### 5.1 Purchase Flow
- Provide a clear primary journey and confirmation state.
- Preserve idempotency across retries and interrupted sessions.
- Record observable outcomes for product and operational analysis.
{improvements}{later}{requested}
## 6. Non-Functional Requirements
- Constraint: {user_constraints or "Deliver a focused, measurable MVP."}
- Accessible keyboard and screen-reader behavior.
- Structured logs without secrets or hidden model reasoning.

## 7. Metrics and Business Rules
| Metric | Target | Source |
|---|---|---|
| Purchase completion | [待确认] | Set after launch data |

## 8. Assumptions and Open Questions
| Item | Type | Why | Decision affected | Validation | Owner |
|---|---|---|---|---|---|
| Launch price | [假设] | Needed to design checkout | Pricing page | Price test | PM |
{PRD_COMPLETION_MARKER}
"""

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
        generation_mode: GenerationMode = GenerationMode.STANDARD,
    ) -> AsyncIterator[ProviderTextEvent]:
        del baseline_prd, output_language, generation_mode
        content = self._prd(
            user_idea,
            target_audience,
            user_constraints,
            iteration,
            revision_plan,
        )
        for start in range(0, len(content), self.chunk_size):
            await self._sleep(self.generator_delay)
            yield ProviderTextEvent(
                delta=content[start : start + self.chunk_size],
                model="mock-prd-v1",
            )
        input_tokens = max(1, len(user_idea) // 4)
        output_tokens = max(1, len(content) // 4)
        yield ProviderTextEvent(
            model="mock-prd-v1",
            finish_reason="stop",
            usage=TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
        )

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
        context: ReviewContext | None = None,
    ) -> ProviderStructuredResult:
        del output_language
        await self._sleep(self.reviewer_delay)
        resolutions = [
            ResolutionInput(
                finding_id=str(item["finding_id"]),
                status=FindingStatus.RESOLVED,
                note="The revised section now covers it.",
            )
            for item in (context.previous_findings if context else [])
            if item.get("finding_id")
        ]
        value = mock_review_output(
            role,
            score=SCORES[role][min(iteration, 5) - 1],
            findings=mock_findings(role, iteration),
            summary=f"{role.value.title()} review for iteration {iteration}.",
            resolutions=resolutions,
        )
        input_tokens = max(1, len(prd) // 12)
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=80,
            total_tokens=input_tokens + 80,
        )
        return ProviderStructuredResult(
            value=value,
            usage=usage,
            model="mock-review-v1",
        )

    async def generate_revision_plan(
        self,
        *,
        evaluation: EvaluationResult,
        iteration: int,
        user_override: str | None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
        context: OptimizerContext | None = None,
    ) -> ProviderStructuredResult:
        del iteration, output_language, context
        await self._sleep(self.optimizer_delay)
        items: list[RevisionItemInput] = []
        declined: list[DeclinedFinding] = []
        for finding in evaluation.combined_feedback:
            if finding.finding_id is None:
                continue
            if finding.severity is FeedbackSeverity.OPTIONAL:
                # Optional polish is declined rather than padding the plan,
                # matching the instruction the real optimizer prompt carries.
                declined.append(
                    DeclinedFinding(
                        finding_id=finding.finding_id,
                        reason="Low-impact polish; not worth a revision round.",
                    )
                )
                continue
            section = finding.section or "5. Detailed Requirements"
            items.append(
                RevisionItemInput(
                    change_type=(
                        ChangeType.ADD
                        if finding.category is FindingCategory.MISSING_FLOW
                        else ChangeType.UPDATE
                    ),
                    source_finding_ids=[finding.finding_id, *finding.merged_from],
                    target_sections=[section],
                    affected_sections=[],
                    issue=finding.title or finding.issue,
                    reason=finding.user_impact or finding.issue,
                    required_change=finding.recommendation,
                    expected_result=f"{section} states the rule once, testably.",
                    must_preserve=[],
                    priority=_PRIORITY[finding.severity],
                )
            )
        if user_override:
            items.append(
                RevisionItemInput(
                    change_type=ChangeType.ADD,
                    source_finding_ids=["user"],
                    target_sections=["5.9 User Requirements"],
                    affected_sections=[],
                    issue="User-requested refinement",
                    reason="The user asked for it.",
                    required_change=user_override,
                    expected_result="The requirement appears in the PRD.",
                    must_preserve=[],
                    priority=RevisionPriority.HIGH,
                )
            )
        plan = OptimizerOutput(
            objective="Resolve all high-priority review findings.",
            items=items,
            declined_findings=declined,
        )
        usage = TokenUsage(input_tokens=120, output_tokens=100, total_tokens=220)
        return ProviderStructuredResult(
            value=plan.model_dump(mode="json"),
            usage=usage,
            model="mock-optimizer-v1",
        )

    async def repair_structured(
        self,
        *,
        kind: str,
        raw_value: Any,
        validation_error: str,
        role: ReviewRole | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> ProviderStructuredResult:
        del raw_value, validation_error, output_language
        if kind == "review" and role is not None:
            value = mock_review_output(
                role,
                score=50,
                summary="Repaired mock response.",
                findings=[
                    _finding(
                        "Original response was invalid",
                        FeedbackSeverity.SHOULD_FIX,
                        FindingCategory.OTHER,
                        "1. Product Overview",
                        "The first response did not match the schema.",
                        "The original response was invalid.",
                        "The review had to be repaired.",
                        "Review the repaired response.",
                    )
                ],
            )
        else:
            value = OptimizerOutput(
                objective="Repaired mock revision plan."
            ).model_dump(mode="json")
        return ProviderStructuredResult(
            value=value,
            usage=TokenUsage(input_tokens=10, output_tokens=10, total_tokens=20),
            model="mock-repair-v1",
        )
