from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from backend.language import DEFAULT_OUTPUT_LANGUAGE
from backend.prd_document import PRD_COMPLETION_MARKER
from backend.providers.base import (
    LLMProvider,
    ProviderStructuredResult,
    ProviderTextEvent,
)
from backend.schemas import (
    EvaluationResult,
    FeedbackItem,
    FeedbackSeverity,
    ReviewRole,
    RevisionItem,
    RevisionPlan,
    RevisionPriority,
    RevisionSource,
    RoleReview,
    TokenUsage,
)

SCORES: dict[ReviewRole, tuple[int, ...]] = {
    ReviewRole.TECH: (65, 88, 90, 92, 94),
    ReviewRole.UX: (70, 89, 91, 93, 95),
    ReviewRole.BIZ: (78, 87, 89, 91, 93),
}

#: Findings a first draft genuinely blocks on: each names an unbuildable core
#: flow or a real risk, matching the `must_fix` criteria in the reviewer rubric.
BLOCKING_FEEDBACK: dict[ReviewRole, tuple[str, str]] = {
    ReviewRole.TECH: (
        "Payment gateway failures have no defined handling, so the purchase "
        "flow cannot be built.",
        "Specify idempotent retries, timeout behaviour, and a terminal failure "
        "state for every gateway call.",
    ),
    ReviewRole.UX: (
        "A failed purchase leaves the listener with no visible state, so the "
        "core journey dead-ends.",
        "Define the failure screen, its retry affordance, and an accessible "
        "error announcement.",
    ),
    ReviewRole.BIZ: (
        "Refunds move money with no stated policy, which is an unmanaged "
        "financial and compliance risk.",
        "Define refund eligibility, who approves it, and how a refund settles "
        "against the creator payout.",
    ),
}

#: Real gaps that do not stop the document from shipping.
IMPROVEMENT_FEEDBACK: dict[ReviewRole, tuple[str, str]] = {
    ReviewRole.TECH: (
        "Fraud protection is described qualitatively.",
        "Add velocity limits, audit events, and a manual review queue.",
    ),
    ReviewRole.UX: (
        "Offline recovery is mentioned but not specified per screen.",
        "Describe what each purchase screen shows once connectivity drops.",
    ),
    ReviewRole.BIZ: (
        "Guardrail metrics have no thresholds.",
        "Give dispute rate, churn, and fraud rate an owner and a threshold.",
    ),
}

#: Polish. Present so the UI has a third tier to render, never a blocker.
OPTIONAL_FEEDBACK: dict[ReviewRole, tuple[tuple[str, str], ...]] = {
    ReviewRole.TECH: (
        (
            "Log retention is unspecified.",
            "State a retention window for structured purchase logs.",
        ),
        (
            "The client cache strategy could be more concrete.",
            "Name the cache layer used for the creator catalogue.",
        ),
    ),
    ReviewRole.UX: (
        (
            "First-run onboarding could be warmer.",
            "Add a one-screen explanation of what a single-episode purchase is.",
        ),
        (
            "Receipt wording could be friendlier.",
            "Reword the receipt copy in the listener's own terms.",
        ),
    ),
    ReviewRole.BIZ: (
        (
            "Pricing sensitivity is not modelled.",
            "Add a short sensitivity table for two candidate price points.",
        ),
        (
            "Creator-side reporting could go deeper.",
            "Add a per-episode revenue breakdown to the creator dashboard.",
        ),
    ),
}


def mock_feedback(role: ReviewRole, iteration: int) -> list[FeedbackItem]:
    """Three tiers per reviewer, with the blockers cleared after the first pass.

    Iteration 1 carries one `must_fix` per role so the quality gate has
    something real to hold the run for; from iteration 2 on only advice remains,
    which is exactly the "score target met, suggestions still open" state the
    dashboard has to present as finished.
    """
    items: list[FeedbackItem] = []
    if iteration <= 1:
        issue, recommendation = BLOCKING_FEEDBACK[role]
        items.append(
            FeedbackItem(
                severity=FeedbackSeverity.MUST_FIX,
                issue=issue,
                recommendation=recommendation,
            )
        )
    issue, recommendation = IMPROVEMENT_FEEDBACK[role]
    items.append(
        FeedbackItem(
            severity=FeedbackSeverity.SHOULD_FIX,
            issue=issue,
            recommendation=recommendation,
        )
    )
    items.extend(
        FeedbackItem(
            severity=FeedbackSeverity.OPTIONAL,
            issue=issue,
            recommendation=recommendation,
        )
        for issue, recommendation in OPTIONAL_FEEDBACK[role]
    )
    return items


#: `must_fix` findings must reach the next version, so they plan as `high`.
SEVERITY_PRIORITY: dict[FeedbackSeverity, RevisionPriority] = {
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
## Reliability, Refunds, and Risk Controls
- Gateway Error & Retry Fallbacks use idempotency keys and bounded retries.
- Refund requests expose pending, approved, and rejected states.
- Fraud protection combines velocity limits, audit events, and manual review.
- Creator payout reconciliation separates settled, refunded, and disputed funds.

## Guardrail Metrics
- Payment failure rate, dispute rate, refund completion time, creator churn,
  listener conversion, and support contacts per purchase.
"""
        later = ""
        if iteration >= 3:
            later = """
## Operational Readiness
- Define ownership, incident severity, rollback criteria, and support runbooks.
- Segment metrics by platform, market, creator cohort, and accessibility mode.
"""
        # A revision plan changes the document, never narrates itself: no
        # "Applied revision plan:" scaffolding, and sections the plan did not
        # name come out identical round to round (the stability test asserts
        # that). A user override is a real requirement, so it lands as content
        # in the section the plan targets.
        requested = ""
        override = revision_plan.user_override if revision_plan else None
        if override:
            requested = f"""
## User Requirements
- {override}
"""
        return f"""# Product Requirements Document — Version {iteration}

## Product Idea
{user_idea}

## Audience
{target_audience or "Product teams and their customers"}

## Constraints
{user_constraints or "Deliver a focused, measurable MVP."}

## Problem and Outcome
Users need a trustworthy flow with explicit success, failure, and recovery
states. The MVP will validate demand while protecting user and operator trust.

## Functional Requirements
1. Provide a clear primary journey and confirmation state.
2. Preserve idempotency across retries and interrupted sessions.
3. Record observable outcomes for product and operational analysis.

## Non-Functional Requirements
- Accessible keyboard and screen-reader behavior.
- Structured logs without secrets or hidden model reasoning.
- Explicit timeout, retry, and cancellation behavior.
{improvements}{later}{requested}
## Acceptance Criteria
- Happy, empty, invalid, offline, and provider-failure paths are testable.
- Metrics have owners, definitions, and guardrail thresholds.
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
    ) -> AsyncIterator[ProviderTextEvent]:
        del baseline_prd, output_language
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
    ) -> ProviderStructuredResult:
        del output_language
        await self._sleep(self.reviewer_delay)
        score = SCORES[role][min(iteration, 5) - 1]
        value = RoleReview(
            role=role,
            score=score,
            summary=f"{role.value.title()} review for iteration {iteration}.",
            strengths=["Clear scope", "Measurable acceptance criteria"],
            feedback=mock_feedback(role, iteration),
        )
        input_tokens = max(1, len(prd) // 12)
        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=80,
            total_tokens=input_tokens + 80,
        )
        return ProviderStructuredResult(
            value=value.model_dump(mode="json"),
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
    ) -> ProviderStructuredResult:
        del output_language
        await self._sleep(self.optimizer_delay)
        seen: dict[str, RevisionItem] = {}
        items: list[RevisionItem] = []
        for review in (evaluation.tech, evaluation.ux, evaluation.biz):
            for feedback in review.feedback:
                if feedback.severity is FeedbackSeverity.OPTIONAL:
                    # Optional polish is dropped rather than padding the plan,
                    # matching the instruction the real optimizer prompt carries.
                    continue
                key = feedback.issue.casefold().strip()
                source = RevisionSource(review.role.value)
                if key in seen:
                    existing = seen[key]
                    if source not in existing.source_roles:
                        existing.source_roles.append(source)
                    continue
                item = RevisionItem(
                    source_role=source,
                    source_roles=[source],
                    issue=feedback.issue,
                    required_change=feedback.recommendation,
                    target_section="Requirements",
                    priority=SEVERITY_PRIORITY[feedback.severity],
                )
                seen[key] = item
                items.append(item)
        if user_override:
            items.append(
                RevisionItem(
                    source_role=RevisionSource.USER,
                    source_roles=[RevisionSource.USER],
                    issue="User-requested refinement",
                    required_change=user_override,
                    target_section="User Requirements",
                    priority=RevisionPriority.HIGH,
                )
            )
        plan = RevisionPlan(
            iteration=iteration,
            objective="Resolve all high-priority review findings.",
            items=items,
            user_override=user_override,
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
        del validation_error, output_language
        if kind == "review" and role is not None:
            value = RoleReview(
                role=role,
                score=50,
                summary="Repaired mock response.",
                feedback=[
                    FeedbackItem(
                        severity=FeedbackSeverity.SHOULD_FIX,
                        issue="The original response was invalid.",
                        recommendation="Review the repaired response.",
                    )
                ],
            ).model_dump(mode="json")
        else:
            value = RevisionPlan(
                iteration=1,
                objective="Repaired mock revision plan.",
            ).model_dump(mode="json")
        return ProviderStructuredResult(
            value=value,
            usage=TokenUsage(input_tokens=10, output_tokens=10, total_tokens=20),
            model="mock-repair-v1",
        )
