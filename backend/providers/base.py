from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.language import DEFAULT_OUTPUT_LANGUAGE
from backend.schemas import (
    EvaluationResult,
    GenerationMode,
    ReviewRole,
    RevisionPlan,
    TokenUsage,
)


class ProviderTextEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta: str = ""
    usage: TokenUsage | None = None
    model: str
    finish_reason: str | None = None


class ProviderStructuredResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    value: Any
    usage: TokenUsage
    model: str
    finish_reason: str = "stop"


class UserRequirements(BaseModel):
    """What the user asked for, verbatim. Reviewers and the optimizer both read it."""

    model_config = ConfigDict(extra="forbid")

    user_idea: str
    target_audience: str | None = None
    user_constraints: str | None = None


class ReviewContext(BaseModel):
    """Everything a reviewer needs beyond the document itself.

    Reviewers used to receive only the PRD, so they could judge whether it was
    complete but never whether it did what the user asked.
    """

    model_config = ConfigDict(extra="forbid")

    requirements: UserRequirements
    automated_checks: list[str] = Field(default_factory=list)
    previous_findings: list[dict[str, Any]] = Field(default_factory=list)


class OptimizerContext(BaseModel):
    """The optimizer's view: the document to revise and the findings against it.

    ``findings`` is the aggregator's de-duplicated list only. The per-role
    feedback is not sent again: in run 9fa59292 the duplicate copy was 43% of the
    optimizer's input.
    """

    model_config = ConfigDict(extra="forbid")

    requirements: UserRequirements
    prd: str
    """The full baseline document, or an outline plus the relevant sections."""
    prd_is_excerpt: bool = False
    reviewed_version: int
    baseline_version: int
    findings: list[dict[str, Any]] = Field(default_factory=list)
    role_scores: dict[str, int] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)


class LLMProvider(ABC):
    is_mock: bool = False

    @abstractmethod
    def stream_prd(
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
    ) -> AsyncIterator[ProviderTextEvent]: ...

    @abstractmethod
    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
        context: ReviewContext | None = None,
    ) -> ProviderStructuredResult:
        """Return a ``ReviewerOutput``-shaped value (no total score)."""

    @abstractmethod
    async def generate_revision_plan(
        self,
        *,
        evaluation: EvaluationResult,
        iteration: int,
        user_override: str | None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
        context: OptimizerContext | None = None,
    ) -> ProviderStructuredResult:
        """Return an ``OptimizerOutput``-shaped value."""

    @abstractmethod
    async def repair_structured(
        self,
        *,
        kind: str,
        raw_value: Any,
        validation_error: str,
        role: ReviewRole | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> ProviderStructuredResult: ...
