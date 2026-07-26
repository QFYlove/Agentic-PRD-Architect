from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.schemas import (
    EvaluationResult,
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
    ) -> AsyncIterator[ProviderTextEvent]: ...

    @abstractmethod
    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
    ) -> ProviderStructuredResult: ...

    @abstractmethod
    async def generate_revision_plan(
        self,
        *,
        evaluation: EvaluationResult,
        iteration: int,
        user_override: str | None,
    ) -> ProviderStructuredResult: ...

    @abstractmethod
    async def repair_structured(
        self,
        *,
        kind: str,
        raw_value: Any,
        validation_error: str,
        role: ReviewRole | None = None,
    ) -> ProviderStructuredResult: ...
