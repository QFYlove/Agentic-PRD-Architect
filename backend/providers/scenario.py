from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Literal

from backend.errors import ProviderAuthenticationError
from backend.language import DEFAULT_OUTPUT_LANGUAGE
from backend.providers.base import ProviderStructuredResult, ProviderTextEvent
from backend.providers.mock import MockLLMProvider
from backend.schemas import ReviewRole, RevisionPlan, TokenUsage

E2EScenario = Literal[
    "happy",
    "malformed_structured",
    "provider_timeout",
    "reviewer_failure",
]
E2E_SCENARIOS: set[str] = {
    "happy",
    "malformed_structured",
    "provider_timeout",
    "reviewer_failure",
}


class ScenarioController:
    def __init__(self) -> None:
        self.scenario: E2EScenario = "happy"

    def set(self, scenario: str) -> E2EScenario:
        if scenario not in E2E_SCENARIOS:
            raise ValueError("Unsupported E2E scenario")
        self.scenario = scenario  # type: ignore[assignment]
        return self.scenario


class ScenarioMockLLMProvider(MockLLMProvider):
    """Deterministic failure injection available only in explicit E2E test mode."""

    def __init__(
        self,
        *,
        controller: ScenarioController,
        timeout_delay: float = 2.0,
        delays_enabled: bool = True,
        chunk_size: int = 72,
        generator_delay: float = 0.01,
        reviewer_delay: float = 0.02,
        optimizer_delay: float = 0.02,
        reviewer_stagger: float = 0.0,
    ) -> None:
        super().__init__(
            delays_enabled=delays_enabled,
            chunk_size=chunk_size,
            generator_delay=generator_delay,
            reviewer_delay=reviewer_delay,
            optimizer_delay=optimizer_delay,
        )
        self.controller = controller
        self.timeout_delay = timeout_delay
        self.reviewer_stagger = reviewer_stagger

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
        if self.controller.scenario == "provider_timeout":
            await asyncio.sleep(self.timeout_delay)
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

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> ProviderStructuredResult:
        if self.delays_enabled and self.reviewer_stagger > 0:
            multiplier = {
                ReviewRole.TECH: 0,
                ReviewRole.UX: 1,
                ReviewRole.BIZ: 2,
            }[role]
            await asyncio.sleep(self.reviewer_stagger * multiplier)
        if role is ReviewRole.TECH:
            if self.controller.scenario == "reviewer_failure":
                raise ProviderAuthenticationError("Injected permanent failure")
            if self.controller.scenario == "malformed_structured":
                return ProviderStructuredResult(
                    value={"role": "tech", "score": 999},
                    usage=TokenUsage(
                        input_tokens=1,
                        output_tokens=1,
                        total_tokens=2,
                    ),
                    model="mock-invalid-v1",
                )
        return await super().generate_review(
            role=role,
            prd=prd,
            iteration=iteration,
            output_language=output_language,
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
        if self.controller.scenario == "malformed_structured":
            return ProviderStructuredResult(
                value={"still": "invalid"},
                usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
                model="mock-invalid-repair-v1",
            )
        return await super().repair_structured(
            kind=kind,
            raw_value=raw_value,
            validation_error=validation_error,
            role=role,
            output_language=output_language,
        )
