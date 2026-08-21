from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.language import DEFAULT_OUTPUT_LANGUAGE


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    GENERATING = "GENERATING"
    REVIEWING = "REVIEWING"
    AGGREGATING = "AGGREGATING"
    OPTIMIZING = "OPTIMIZING"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    PAUSED = "PAUSED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    COMPLETED = "COMPLETED"
    MAX_ITERATIONS_REACHED = "MAX_ITERATIONS_REACHED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class NodeStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ReviewRole(StrEnum):
    TECH = "tech"
    UX = "ux"
    BIZ = "biz"


class RevisionSource(StrEnum):
    TECH = "tech"
    UX = "ux"
    BIZ = "biz"
    USER = "user"


class RevisionPriority(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FeedbackSeverity(StrEnum):
    """How much a single reviewer finding should be allowed to block a run.

    A flat list of feedback strings makes "the payment flow has no failure path"
    and "this metric could be quantified further" look identical, so a run that
    reached its score target still reads as unfinished. Only ``MUST_FIX`` gates
    completion; the other two tiers are advice that survives a finished PRD.
    """

    MUST_FIX = "must_fix"
    SHOULD_FIX = "should_fix"
    OPTIONAL = "optional"


#: Highest first. Used to resolve one issue raised at two severities.
SEVERITY_ORDER: tuple[FeedbackSeverity, ...] = (
    FeedbackSeverity.MUST_FIX,
    FeedbackSeverity.SHOULD_FIX,
    FeedbackSeverity.OPTIONAL,
)


class RunEventType(StrEnum):
    RUN_STARTED = "run_started"
    STATUS_CHANGED = "status_changed"
    NODE_STARTED = "node_started"
    PRD_DELTA = "prd_delta"
    PRD_STREAM_RESET = "prd_stream_reset"
    PRD_GENERATED = "prd_generated"
    REVIEW_COMPLETED = "review_completed"
    SCORES_UPDATED = "scores_updated"
    REVISION_PLANNED = "revision_planned"
    PAUSE_REQUESTED = "pause_requested"
    RUN_PAUSED = "run_paused"
    RUN_RESUMED = "run_resumed"
    TELEMETRY_UPDATED = "telemetry_updated"
    RUN_COMPLETED = "run_completed"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    RUN_CANCELLED = "run_cancelled"
    RUN_FAILED = "run_failed"


class CreateRunRequest(StrictModel):
    user_idea: str = Field(min_length=10, max_length=5000)
    target_audience: str | None = Field(default=None, max_length=1000)
    user_constraints: str | None = Field(default=None, max_length=2000)
    quality_threshold: float = Field(default=85.0, ge=50, le=100)
    max_iterations: int = Field(default=3, ge=1, le=5)

    @field_validator("user_idea")
    @classmethod
    def validate_user_idea(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("user_idea must contain at least 10 non-space characters")
        return value

    @field_validator("target_audience", "user_constraints")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ResumeRunRequest(StrictModel):
    user_override: str | None = Field(default=None, max_length=2000)

    @field_validator("user_override")
    @classmethod
    def normalize_override(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class FeedbackItem(StrictModel):
    """One reviewer finding, with the severity that decides whether it blocks."""

    severity: FeedbackSeverity
    issue: str = Field(min_length=1, max_length=2000)
    recommendation: str = Field(min_length=1, max_length=2000)


def _coerce_feedback(value: Any) -> Any:
    """Accept the legacy ``list[str]`` shape that persisted snapshots still hold.

    Runs recorded before severity existed stored bare strings. They deserialize
    as ``should_fix`` -- never ``must_fix``, because promoting old advice to a
    blocker would retroactively un-complete finished runs. Structured items are
    left untouched so a malformed model response still fails loudly.
    """
    if not isinstance(value, list):
        return value
    coerced: list[Any] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            coerced.append(
                {
                    "severity": FeedbackSeverity.SHOULD_FIX.value,
                    "issue": text,
                    "recommendation": text,
                }
            )
        else:
            coerced.append(item)
    return coerced


class RoleReview(StrictModel):
    role: ReviewRole
    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=2000)
    strengths: list[str] = Field(default_factory=list)
    feedback: list[FeedbackItem] = Field(default_factory=list)

    _coerce_legacy_feedback = field_validator("feedback", mode="before")(
        _coerce_feedback
    )

    def feedback_by_severity(self, severity: FeedbackSeverity) -> list[FeedbackItem]:
        return [item for item in self.feedback if item.severity is severity]


class EvaluationResult(StrictModel):
    tech: RoleReview
    ux: RoleReview
    biz: RoleReview
    overall_score: float = Field(ge=0, le=100)
    combined_feedback: list[FeedbackItem] = Field(default_factory=list)

    _coerce_legacy_combined = field_validator("combined_feedback", mode="before")(
        _coerce_feedback
    )

    @model_validator(mode="after")
    def validate_roles_and_score(self) -> EvaluationResult:
        expected_roles = (
            (self.tech.role, ReviewRole.TECH),
            (self.ux.role, ReviewRole.UX),
            (self.biz.role, ReviewRole.BIZ),
        )
        if any(actual != expected for actual, expected in expected_roles):
            raise ValueError("Review fields must contain their matching role")

        expected_score = round(
            (self.tech.score + self.ux.score + self.biz.score) / 3,
            1,
        )
        if self.overall_score != expected_score:
            raise ValueError(
                f"overall_score must be the server-computed average: {expected_score}"
            )
        return self

    def severity_counts(self) -> dict[str, int]:
        """How many open findings sit at each tier, across all three reviewers.

        Derived on demand rather than stored: the counts must never be able to
        disagree with the reviews they summarise.
        """
        counts = {severity.value: 0 for severity in SEVERITY_ORDER}
        for item in self.combined_feedback:
            counts[item.severity.value] += 1
        return counts

    @property
    def must_fix_count(self) -> int:
        return sum(
            1
            for item in self.combined_feedback
            if item.severity is FeedbackSeverity.MUST_FIX
        )


class RevisionItem(StrictModel):
    source_role: RevisionSource
    source_roles: list[RevisionSource] = Field(default_factory=list)
    issue: str = Field(min_length=1, max_length=2000)
    required_change: str = Field(min_length=1, max_length=4000)
    target_section: str = Field(min_length=1, max_length=500)
    priority: RevisionPriority

    @model_validator(mode="after")
    def normalize_source_roles(self) -> RevisionItem:
        if not self.source_roles:
            self.source_roles = [self.source_role]
        elif self.source_role not in self.source_roles:
            raise ValueError("source_role must be included in source_roles")
        self.source_roles = list(dict.fromkeys(self.source_roles))
        return self


class RevisionPlan(StrictModel):
    iteration: int = Field(ge=1, le=5)
    objective: str = Field(min_length=1, max_length=2000)
    items: list[RevisionItem] = Field(default_factory=list)
    user_override: str | None = Field(default=None, max_length=2000)


class TokenUsage(StrictModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_total(self) -> TokenUsage:
        expected = self.input_tokens + self.output_tokens
        if self.total_tokens != expected:
            raise ValueError(f"total_tokens must equal input + output: {expected}")
        return self


class RunError(StrictModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    retryable: bool = False


class NodeTiming(StrictModel):
    """How long one node call took, and what it spent.

    A 500-second run gives no clue which of six sequential-and-parallel model
    calls owned the time. One record per completed call answers that without a
    profiler: the node, which version it was working on, which attempt, and the
    wall-clock seconds between the node starting (or its previous attempt ending)
    and this call returning.

    ``succeeded`` is false for an attempt that burned tokens and then produced an
    unusable document -- those are exactly the calls a slow run needs to show, and
    hiding them would make the recorded time not add up to the elapsed time.
    """

    node: str = Field(min_length=1, max_length=64)
    version: int = Field(ge=1, le=5)
    attempt: int = Field(default=1, ge=1)
    seconds: float = Field(ge=0)
    succeeded: bool = True
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class PRDVersion(StrictModel):
    version: int = Field(ge=1, le=5)
    content: str
    created_at: datetime
    evaluation: EvaluationResult | None = None
    revision_plan: RevisionPlan | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)


def utc_now() -> datetime:
    return datetime.now(UTC)


class PRDRunState(StrictModel):
    run_id: UUID
    user_idea: str
    target_audience: str | None = None
    user_constraints: str | None = None
    output_language: str = DEFAULT_OUTPUT_LANGUAGE
    """The language every agent in this run must write in.

    Derived once from the user's own text at creation time rather than per call,
    so the PRD, all three reviews, and the revision plan cannot disagree.
    """
    current_iteration: int = Field(default=1, ge=1, le=5)
    max_iterations: int = Field(default=3, ge=1, le=5)
    quality_threshold: float = Field(default=85.0, ge=50, le=100)
    status: RunStatus = RunStatus.QUEUED
    active_node: str | None = None
    versions: list[PRDVersion] = Field(default_factory=list)
    current_prd: str = ""
    current_prd_attempt: int = Field(default=1, ge=1)
    """Which generation attempt produced ``current_prd``.

    ``prd_delta`` is transient, so a reconnecting client rebuilds its streaming
    draft from ``current_prd``; without this field it cannot tell whether that
    text belongs to attempt 1 or to a retry, and would discard every subsequent
    delta of the attempt actually in flight.
    """
    latest_evaluation: EvaluationResult | None = None
    best_version: int | None = Field(default=None, ge=1, le=5)
    """Which version scored highest so far, independent of which came last.

    ``max_iterations`` is an attempt budget, not a guarantee of improvement: a
    later version may legitimately score lower. Without this field the run's
    outcome is read off the latest iteration, which presents a worse v3 as the
    result of a run whose best work was v2.
    """
    best_score: float | None = Field(default=None, ge=0, le=100)
    """The overall score of ``best_version``, recorded as the reviewers gave it.

    Reviewer scores are never rewritten and never clamped to a running maximum;
    only the pointer to the best one is kept.
    """
    reviews: dict[ReviewRole, RoleReview] = Field(default_factory=dict)
    pending_revision_plan: RevisionPlan | None = None
    pending_user_override: str | None = None
    node_statuses: dict[str, NodeStatus] = Field(default_factory=dict)
    total_tokens: TokenUsage = Field(default_factory=TokenUsage)
    node_tokens: dict[str, TokenUsage] = Field(default_factory=dict)
    node_timings: list[NodeTiming] = Field(default_factory=list)
    """One entry per completed node call, in the order the calls returned.

    A list rather than a per-node total: the same node runs once per iteration,
    and "which node is slow" and "is it getting slower each round" are both
    questions this answers only if the calls stay separate.
    """
    estimated_cost_usd: float | None = Field(default=None, ge=0)
    cost_available: bool = False
    is_mock: bool = True
    elapsed_seconds: float = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: RunError | None = None

    @model_validator(mode="after")
    def validate_iteration(self) -> PRDRunState:
        if self.current_iteration > self.max_iterations:
            raise ValueError("current_iteration cannot exceed max_iterations")
        return self


class RunSnapshot(PRDRunState):
    latest_event_sequence: int = Field(default=0, ge=0)


class RunSummary(StrictModel):
    run_id: UUID
    user_idea: str
    status: RunStatus
    current_iteration: int
    max_iterations: int
    latest_score: float | None = Field(default=None, ge=0, le=100)
    best_version: int | None = Field(default=None, ge=1, le=5)
    best_score: float | None = Field(default=None, ge=0, le=100)
    created_at: datetime
    updated_at: datetime


class RunListResponse(StrictModel):
    items: list[RunSummary]
    total: int = Field(ge=0)


class RunEvent(StrictModel):
    run_id: UUID
    sequence: int = Field(ge=1)
    event: RunEventType
    timestamp: datetime = Field(default_factory=utc_now)
    iteration: int = Field(ge=1, le=5)
    payload: dict[str, Any] = Field(default_factory=dict)


class ErrorDetail(StrictModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(StrictModel):
    error: ErrorDetail


class HealthResponse(StrictModel):
    status: str
    mock_mode: bool
    provider: str


class CreateRunResponse(StrictModel):
    run_id: UUID
    status: RunStatus
    events_url: str
    created_at: datetime


class ControlResponse(StrictModel):
    run_id: UUID
    status: RunStatus
    message: str
