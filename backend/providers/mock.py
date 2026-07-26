from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from backend.providers.base import (
    LLMProvider,
    ProviderStructuredResult,
    ProviderTextEvent,
)
from backend.schemas import (
    EvaluationResult,
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

FEEDBACK: dict[ReviewRole, tuple[str, ...]] = {
    ReviewRole.TECH: (
        "Define payment gateway failure handling and idempotent retries.",
        "Add fraud detection, rate limits, and audit logging.",
    ),
    ReviewRole.UX: (
        "Document refund status, offline recovery, and accessible errors.",
        "Add clear retry, receipt, and account-history journeys.",
    ),
    ReviewRole.BIZ: (
        "Define refund economics and creator payout reconciliation.",
        "Add guardrail metrics for disputes, churn, and fraud.",
    ),
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
        plan_summary = ""
        if revision_plan is not None:
            changes = "; ".join(item.required_change for item in revision_plan.items)
            plan_summary = f"\nApplied revision plan: {changes}\n"
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
{improvements}{later}{plan_summary}
## Acceptance Criteria
- Happy, empty, invalid, offline, and provider-failure paths are testable.
- Metrics have owners, definitions, and guardrail thresholds.
"""

    async def stream_prd(
        self,
        *,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan: RevisionPlan | None,
    ) -> AsyncIterator[ProviderTextEvent]:
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
    ) -> ProviderStructuredResult:
        await self._sleep(self.reviewer_delay)
        score = SCORES[role][min(iteration, 5) - 1]
        value = RoleReview(
            role=role,
            score=score,
            summary=f"{role.value.title()} review for iteration {iteration}.",
            strengths=["Clear scope", "Measurable acceptance criteria"],
            feedback=list(FEEDBACK[role]),
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
    ) -> ProviderStructuredResult:
        await self._sleep(self.optimizer_delay)
        seen: dict[str, RevisionItem] = {}
        items: list[RevisionItem] = []
        for review in (evaluation.tech, evaluation.ux, evaluation.biz):
            for feedback in review.feedback:
                key = feedback.casefold().strip()
                source = RevisionSource(review.role.value)
                if key in seen:
                    existing = seen[key]
                    if source not in existing.source_roles:
                        existing.source_roles.append(source)
                    continue
                item = RevisionItem(
                    source_role=source,
                    source_roles=[source],
                    issue=feedback,
                    required_change=feedback,
                    target_section="Requirements",
                    priority=RevisionPriority.HIGH,
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
    ) -> ProviderStructuredResult:
        del validation_error
        if kind == "review" and role is not None:
            value = RoleReview(
                role=role,
                score=50,
                summary="Repaired mock response.",
                feedback=["Review the repaired response."],
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
