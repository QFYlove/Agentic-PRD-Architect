"""What the five V3 model calls return, and the gateway that makes them.

Every structured output is validated twice: once by these Pydantic shapes, and
again by the service layer against the project's real data (item codes exist,
evidence is found in the document, statuses a model may not set are lowered).
The shapes only make malformed output fail fast; the rules live in code.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from pydantic import Field

from backend.providers.base import ProviderStructuredResult, ProviderTextEvent
from backend.schemas import DimensionScoreInput
from backend.v3.models import (
    AnalystKind,
    ChangeType,
    Group,
    ItemStatus,
    Priority,
    Reviewer,
    Severity,
    SourceKind,
    Strict,
)

# --- Explorer -----------------------------------------------------------------


class ExtractedItem(Strict):
    code: str | None = None
    """An existing item to update, or ``None`` for a new one."""
    group: Group
    content: str = Field(min_length=1, max_length=600)
    status: ItemStatus
    source_kind: SourceKind
    source_quote: str = Field(default="", max_length=600)
    priority: Priority = Priority.P1
    reason: str = Field(default="", max_length=600)


class NextQuestion(Strict):
    text: str = Field(min_length=1, max_length=400)
    purpose: str = Field(min_length=1, max_length=400)
    target_group: Group
    priority: Priority
    finding_code: str | None = None


class ExplorerOutput(Strict):
    understanding: str = Field(min_length=1, max_length=1500)
    items: list[ExtractedItem] = Field(default_factory=list, max_length=20)
    questions: list[NextQuestion] = Field(default_factory=list, max_length=5)
    ready_for_brief: bool = False


# --- Analyst ------------------------------------------------------------------


class Opportunity(Strict):
    user_problem: str = Field(min_length=1, max_length=400)
    current_solution: str = Field(min_length=1, max_length=400)
    shortfall: str = Field(min_length=1, max_length=400)
    value: str = Field(min_length=1, max_length=400)
    cost: str = Field(min_length=1, max_length=400)
    assumptions: list[str] = Field(min_length=1, max_length=5)


class AnalystFinding(Strict):
    kind: AnalystKind
    title: str = Field(min_length=1, max_length=120)
    severity: Severity
    evidence_items: list[str] = Field(default_factory=list, max_length=10)
    evidence: str = Field(min_length=1, max_length=800)
    problem: str = Field(min_length=1, max_length=1000)
    impact: str = Field(default="", max_length=600)
    recommendation: str = Field(min_length=1, max_length=1000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    opportunity: Opportunity | None = None


class AnalystOutput(Strict):
    summary: str = Field(min_length=1, max_length=800)
    findings: list[AnalystFinding] = Field(default_factory=list, max_length=10)


# --- Generator ----------------------------------------------------------------


class OutlineEntry(Strict):
    num: str = Field(min_length=1, max_length=12)
    title: str = Field(min_length=1, max_length=80)
    level: int = Field(ge=1, le=2)
    goal: str = Field(default="", max_length=400)
    contents: list[str] = Field(default_factory=list, max_length=10)
    item_codes: list[str] = Field(default_factory=list, max_length=30)
    depends: list[str] = Field(default_factory=list, max_length=10)
    open_points: list[str] = Field(default_factory=list, max_length=10)


class OutlineOutput(Strict):
    title: str = Field(min_length=1, max_length=80)
    sections: list[OutlineEntry] = Field(min_length=1, max_length=30)


# --- Reviewers ----------------------------------------------------------------


class ReviewFinding(Strict):
    title: str = Field(min_length=1, max_length=120)
    severity: Severity
    category: str = Field(default="other", max_length=40)
    section: str = Field(default="", max_length=120)
    evidence: str = Field(default="", max_length=800)
    problem: str = Field(min_length=1, max_length=1200)
    cause: str = Field(default="", max_length=600)
    impact: str = Field(default="", max_length=800)
    recommendation: str = Field(min_length=1, max_length=1200)
    confidence: float | None = Field(default=None, ge=0, le=1)
    related_items: list[str] = Field(default_factory=list, max_length=10)


class ReviewResolution(Strict):
    finding_code: str
    status: str
    """``resolved``, ``partially_resolved`` or ``unresolved``."""
    note: str = Field(default="", max_length=400)


class ReviewerOutput(Strict):
    reviewer: Reviewer
    summary: str = Field(min_length=1, max_length=800)
    strengths: list[str] = Field(default_factory=list, max_length=5)
    risks: list[str] = Field(default_factory=list, max_length=5)
    blocking: bool = False
    dimension_scores: list[DimensionScoreInput]
    findings: list[ReviewFinding] = Field(default_factory=list, max_length=10)
    resolutions: list[ReviewResolution] = Field(default_factory=list)


# --- Optimizer ----------------------------------------------------------------


class OptimizerChange(Strict):
    change_type: ChangeType
    section: str = Field(min_length=1, max_length=40)
    """Section code (``S-03``) or number (``4.1``)."""
    new_title: str | None = Field(default=None, max_length=80)
    reason: str = Field(min_length=1, max_length=600)
    after: str = Field(default="", max_length=20_000)
    finding_codes: list[str] = Field(default_factory=list, max_length=10)
    affected_sections: list[str] = Field(default_factory=list, max_length=10)
    must_preserve: list[str] = Field(default_factory=list, max_length=10)


class DeclinedFinding(Strict):
    finding_code: str
    reason: str = Field(min_length=1, max_length=400)


class OptimizerOutput(Strict):
    objective: str = Field(min_length=1, max_length=600)
    changes: list[OptimizerChange] = Field(default_factory=list, max_length=20)
    declined: list[DeclinedFinding] = Field(default_factory=list)


# --- Gateway ------------------------------------------------------------------


class ModelGateway(Protocol):
    """The transport the five calls share. Prompts and rules stay outside it."""

    is_mock: bool
    provider_name: str
    model: str

    async def structured(
        self,
        *,
        task: str,
        instructions: str,
        payload: dict[str, Any],
        schema: type[Strict],
        language: str,
    ) -> ProviderStructuredResult: ...

    def stream(
        self,
        *,
        task: str,
        instructions: str,
        payload: dict[str, Any],
        language: str,
    ) -> AsyncIterator[ProviderTextEvent]: ...


class CompatibleGateway:
    """Adapts the V2 OpenAI-compatible provider to the V3 calls."""

    is_mock = False

    def __init__(self, provider: Any) -> None:
        self._provider = provider
        self.provider_name = str(provider.provider_name)
        self.model = str(provider.model)

    async def structured(
        self,
        *,
        task: str,
        instructions: str,
        payload: dict[str, Any],
        schema: type[Strict],
        language: str,
    ) -> ProviderStructuredResult:
        result: ProviderStructuredResult = await self._provider.structured_call(
            model_type=schema,
            instructions=instructions,
            payload=payload,
            output_language=language,
        )
        return result

    def stream(
        self,
        *,
        task: str,
        instructions: str,
        payload: dict[str, Any],
        language: str,
    ) -> AsyncIterator[ProviderTextEvent]:
        iterator: AsyncIterator[ProviderTextEvent] = self._provider.stream_call(
            instructions=instructions,
            payload=payload,
            output_language=language,
        )
        return iterator
