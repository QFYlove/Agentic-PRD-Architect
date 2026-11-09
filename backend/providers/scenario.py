from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any, Literal

from backend.errors import ProviderAuthenticationError
from backend.language import DEFAULT_OUTPUT_LANGUAGE
from backend.providers.base import (
    OptimizerContext,
    ProviderStructuredResult,
    ProviderTextEvent,
    ReviewContext,
)
from backend.providers.mock import MockLLMProvider
from backend.schemas import (
    EvaluationResult,
    GenerationMode,
    ReviewRole,
    RevisionPlan,
    TokenUsage,
)

E2EScenario = Literal[
    "happy",
    "malformed_structured",
    "provider_timeout",
    "reviewer_failure",
    "output_truncated",
    "optimizer_failure",
]
E2E_SCENARIOS: set[str] = {
    "happy",
    "malformed_structured",
    "provider_timeout",
    "reviewer_failure",
    "output_truncated",
    "optimizer_failure",
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
        generation_mode: GenerationMode = GenerationMode.STANDARD,
    ) -> AsyncIterator[ProviderTextEvent]:
        if self.controller.scenario == "provider_timeout":
            await asyncio.sleep(self.timeout_delay)
        if (
            self.controller.scenario == "output_truncated"
            and iteration >= 2
            and generation_mode is GenerationMode.STANDARD
        ):
            # v1 lands, then v2 hits the output cap the way run 9fa59292 did. A
            # compact recovery run is not truncated, so recovery can be tested.
            partial = self._prd(
                user_idea, target_audience, user_constraints, iteration, revision_plan
            )
            cut = partial[: len(partial) // 2]
            for start in range(0, len(cut), self.chunk_size):
                await self._sleep(self.generator_delay)
                yield ProviderTextEvent(
                    delta=cut[start : start + self.chunk_size], model="mock-prd-v1"
                )
            yield ProviderTextEvent(
                model="mock-prd-v1",
                finish_reason="length",
                usage=TokenUsage(input_tokens=50, output_tokens=60, total_tokens=110),
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
            generation_mode=generation_mode,
        ):
            yield event

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
        context: ReviewContext | None = None,
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
            context=context,
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
        if self.controller.scenario == "optimizer_failure":
            return ProviderStructuredResult(
                value={"objective": ""},
                usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
                model="mock-invalid-v1",
            )
        return await super().generate_revision_plan(
            evaluation=evaluation,
            iteration=iteration,
            user_override=user_override,
            output_language=output_language,
            context=context,
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
        if self.controller.scenario in {"malformed_structured", "optimizer_failure"}:
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
