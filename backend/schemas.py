from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class RoleReview(StrictModel):
    role: ReviewRole
    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=2000)
    strengths: list[str] = Field(default_factory=list)
    feedback: list[str] = Field(default_factory=list)


class EvaluationResult(StrictModel):
    tech: RoleReview
    ux: RoleReview
    biz: RoleReview
    overall_score: float = Field(ge=0, le=100)
    combined_feedback: list[str] = Field(default_factory=list)

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
    current_iteration: int = Field(default=1, ge=1, le=5)
    max_iterations: int = Field(default=3, ge=1, le=5)
    quality_threshold: float = Field(default=85.0, ge=50, le=100)
    status: RunStatus = RunStatus.QUEUED
    active_node: str | None = None
    versions: list[PRDVersion] = Field(default_factory=list)
    current_prd: str = ""
    latest_evaluation: EvaluationResult | None = None
    reviews: dict[ReviewRole, RoleReview] = Field(default_factory=dict)
    pending_revision_plan: RevisionPlan | None = None
    pending_user_override: str | None = None
    node_statuses: dict[str, NodeStatus] = Field(default_factory=dict)
    total_tokens: TokenUsage = Field(default_factory=TokenUsage)
    node_tokens: dict[str, TokenUsage] = Field(default_factory=dict)
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
