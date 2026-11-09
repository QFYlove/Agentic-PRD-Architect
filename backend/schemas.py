from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.language import DEFAULT_OUTPUT_LANGUAGE
from backend.rubric import (
    DIMENSION_SCORE_MAX,
    DIMENSION_SCORE_MIN,
    dimensions_for,
    resolve_dimension_id,
)


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
    OPTIMIZER = "optimizer"
    """An edit the optimizer proposes on its own -- removing or merging duplicates."""


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

    @classmethod
    def _missing_(cls, value: object) -> FeedbackSeverity | None:
        # The V2 reviewer contract calls the lowest tier `nice_to_have`. It is
        # the same tier, so it is stored under the existing value rather than
        # forking every persisted review and client into two spellings.
        if isinstance(value, str) and value.strip().lower() in {
            "nice_to_have",
            "nice-to-have",
        }:
            return cls.OPTIONAL
        return None


class FindingCategory(StrEnum):
    """What kind of problem a finding is, used for dedup and severity rules."""

    REQUIREMENT_GAP = "requirement_gap"
    LOGIC_ERROR = "logic_error"
    CONTRADICTION = "contradiction"
    MISSING_FLOW = "missing_flow"
    EDGE_CASE = "edge_case"
    STATE_FEEDBACK = "state_feedback"
    TECHNICAL_RISK = "technical_risk"
    DATA_INTEGRITY = "data_integrity"
    SECURITY_PRIVACY = "security_privacy"
    UX_CLARITY = "ux_clarity"
    SCOPE_PRIORITY = "scope_priority"
    BUSINESS_VALUE = "business_value"
    COST_RISK = "cost_risk"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    QUANTIFICATION = "quantification"
    CONSTRAINT_VIOLATION = "constraint_violation"
    OTHER = "other"

    @classmethod
    def _missing_(cls, value: object) -> FindingCategory:
        # An unknown label from a model is still a finding; it just cannot take
        # part in category-specific rules.
        return cls.OTHER


class FindingStatus(StrEnum):
    """Whether a finding raised on one version was closed by the next."""

    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"
    DECLINED = "declined"
    NOT_CHECKED = "not_checked"

    @classmethod
    def _missing_(cls, value: object) -> FindingStatus:
        return cls.NOT_CHECKED


class GateStatus(StrEnum):
    PASSED = "PASSED"
    NEEDS_REVISION = "NEEDS_REVISION"
    BLOCKED = "BLOCKED"
    UNSCORED = "UNSCORED"


class GenerationMode(StrEnum):
    STANDARD = "standard"
    COMPACT = "compact"


class RecoveryMode(StrEnum):
    """How a new run is derived from a finished one. The old run is never edited."""

    RESTART = "restart"
    REGENERATE_COMPACT = "regenerate_compact"
    CONTINUE_FROM_BEST = "continue_from_best"


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
    provider_id: str | None = None
    model_id: str | None = None
    generation_mode: GenerationMode = GenerationMode.STANDARD
    """`compact` asks for a shorter document from the first version on."""

    @model_validator(mode="after")
    def validate_selection_pair(self) -> CreateRunRequest:
        if (self.provider_id is None) != (self.model_id is None):
            raise ValueError("provider_id and model_id must be provided together")
        return self

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


class RecoverRunRequest(StrictModel):
    """Start a new run derived from a finished one. The source run is not edited."""

    mode: RecoveryMode


class FindingObservation(StrictModel):
    """One reviewer's view of a problem that the aggregator merged with others."""

    finding_id: str = Field(min_length=1, max_length=64)
    role: ReviewRole
    severity: FeedbackSeverity
    problem: str = Field(min_length=1, max_length=2000)
    evidence: str | None = Field(default=None, max_length=1000)


class FeedbackItem(StrictModel):
    """One reviewer finding, with the severity that decides whether it blocks.

    ``severity``, ``issue`` and ``recommendation`` are the original contract and
    every persisted review has them. The remaining fields arrived with the V2
    reviewer contract and are optional, so a legacy finding still loads and
    renders; the frontend shows evidence and section only when they exist.
    """

    severity: FeedbackSeverity
    issue: str = Field(min_length=1, max_length=2000)
    recommendation: str = Field(min_length=1, max_length=2000)
    finding_id: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=200)
    category: FindingCategory | None = None
    section: str | None = Field(default=None, max_length=200)
    evidence: str | None = Field(default=None, max_length=1000)
    user_impact: str | None = Field(default=None, max_length=1000)
    source_role: ReviewRole | None = None
    source_roles: list[ReviewRole] = Field(default_factory=list)
    """Every reviewer that raised this problem, after the aggregator merged them."""
    merged_from: list[str] = Field(default_factory=list)
    """Finding ids folded into this one by the aggregator."""
    observations: list[FindingObservation] = Field(default_factory=list)
    """Each merged reviewer's own wording and evidence, kept side by side."""
    confidence: float | None = Field(default=None, ge=0, le=1)
    severity_adjusted_from: FeedbackSeverity | None = None
    """Set when the backend lowered a severity the rubric does not allow."""


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


class DimensionScore(StrictModel):
    """One rubric dimension, scored 1-5 by a reviewer with its reason."""

    dimension: str = Field(min_length=1, max_length=64)
    score: int = Field(ge=DIMENSION_SCORE_MIN, le=DIMENSION_SCORE_MAX)
    rationale: str = Field(min_length=1, max_length=600)
    weight: float | None = Field(default=None, ge=0, le=1)
    """Copied from the rubric by the backend, so a stored review is self-describing."""


class FindingResolution(StrictModel):
    """What happened to one finding from the previous version."""

    finding_id: str = Field(min_length=1, max_length=64)
    status: FindingStatus
    note: str | None = Field(default=None, max_length=600)
    source_version: int | None = Field(default=None, ge=1, le=5)
    title: str | None = Field(default=None, max_length=200)
    severity: FeedbackSeverity | None = None


class RoleReview(StrictModel):
    role: ReviewRole
    score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=2000)
    strengths: list[str] = Field(default_factory=list)
    feedback: list[FeedbackItem] = Field(default_factory=list)
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    """Empty on reviews recorded before the rubric existed (legacy scoring)."""
    rubric_version: str | None = None
    scoring_version: str | None = None
    filtered_findings: int = Field(default=0, ge=0)
    """Findings the backend did not keep: over the cap, or with no evidence."""
    resolutions: list[FindingResolution] = Field(default_factory=list)

    _coerce_legacy_feedback = field_validator("feedback", mode="before")(
        _coerce_feedback
    )

    def feedback_by_severity(self, severity: FeedbackSeverity) -> list[FeedbackItem]:
        return [item for item in self.feedback if item.severity is severity]

    @property
    def is_legacy_scoring(self) -> bool:
        return not self.dimension_scores


class EvaluationResult(StrictModel):
    tech: RoleReview
    ux: RoleReview
    biz: RoleReview
    overall_score: float = Field(ge=0, le=100)
    combined_feedback: list[FeedbackItem] = Field(default_factory=list)
    """The aggregator's de-duplicated findings (legacy runs: a plain concatenation)."""
    findings_before_dedup: int | None = Field(default=None, ge=0)
    gate_status: GateStatus | None = None
    rubric_version: str | None = None
    scoring_version: str | None = None
    finding_resolutions: list[FindingResolution] = Field(default_factory=list)
    """How the previous version's findings fared in this version."""

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


class ChangeType(StrEnum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    REMOVE = "REMOVE"
    CONSOLIDATE = "CONSOLIDATE"
    RETAIN = "RETAIN"

    @classmethod
    def _missing_(cls, value: object) -> ChangeType | None:
        if isinstance(value, str):
            upper = value.strip().upper()
            for member in cls:
                if member.value == upper:
                    return member
        return None


class RevisionItem(StrictModel):
    source_role: RevisionSource
    source_roles: list[RevisionSource] = Field(default_factory=list)
    issue: str = Field(min_length=1, max_length=2000)
    required_change: str = Field(min_length=1, max_length=4000)
    target_section: str = Field(min_length=1, max_length=500)
    priority: RevisionPriority
    item_id: str | None = Field(default=None, max_length=64)
    change_type: ChangeType | None = None
    """None on legacy plans, which only ever added or rewrote content."""
    source_finding_ids: list[str] = Field(default_factory=list)
    target_sections: list[str] = Field(default_factory=list)
    affected_sections: list[str] = Field(default_factory=list)
    """Other sections that state the same rule and must change with it."""
    reason: str | None = Field(default=None, max_length=1000)
    expected_result: str | None = Field(default=None, max_length=1000)
    must_preserve: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_source_roles(self) -> RevisionItem:
        if not self.source_roles:
            self.source_roles = [self.source_role]
        elif self.source_role not in self.source_roles:
            raise ValueError("source_role must be included in source_roles")
        self.source_roles = list(dict.fromkeys(self.source_roles))
        return self


class DeclinedFinding(StrictModel):
    finding_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=600)


class RevisionPlan(StrictModel):
    iteration: int = Field(ge=1, le=5)
    objective: str = Field(min_length=1, max_length=2000)
    items: list[RevisionItem] = Field(default_factory=list)
    user_override: str | None = Field(default=None, max_length=2000)
    declined_findings: list[DeclinedFinding] = Field(default_factory=list)
    plan_version: str | None = None
    """``"v2"`` for plans built from finding ids; None for legacy plans."""


# --- Model-facing contracts -------------------------------------------------
#
# These are the JSON shapes the reviewer and optimizer models are asked to emit.
# They are deliberately not the stored shapes: a reviewer never supplies its own
# role score (the backend computes it from the dimensions), and an optimizer
# never supplies source roles or the iteration (the backend derives both from the
# finding ids it referenced). Keeping them separate is what makes "the model
# cannot set the final score" a property of the schema, not of a prompt.


class FindingInput(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    severity: FeedbackSeverity
    category: FindingCategory
    section: str = Field(max_length=200)
    evidence: str = Field(max_length=1000)
    problem: str = Field(min_length=1, max_length=1500)
    user_impact: str = Field(max_length=1000)
    recommendation: str = Field(min_length=1, max_length=1500)
    confidence: float | None = Field(default=None, ge=0, le=1)


class ResolutionInput(StrictModel):
    finding_id: str = Field(min_length=1, max_length=64)
    status: FindingStatus
    note: str = Field(max_length=600)


class DimensionScoreInput(StrictModel):
    dimension: str = Field(min_length=1, max_length=64)
    score: int = Field(ge=DIMENSION_SCORE_MIN, le=DIMENSION_SCORE_MAX)
    rationale: str = Field(min_length=1, max_length=600)


class ReviewerOutput(StrictModel):
    """What one reviewer model returns. It carries no total score."""

    role: ReviewRole
    summary: str = Field(min_length=1, max_length=2000)
    strengths: list[str] = Field(default_factory=list)
    dimension_scores: list[DimensionScoreInput]
    findings: list[FindingInput] = Field(default_factory=list)
    """May be empty: a review that finds nothing worth fixing says so."""
    resolutions: list[ResolutionInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dimensions(self) -> ReviewerOutput:
        expected = [dimension.id for dimension in dimensions_for(self.role.value)]
        resolved: list[DimensionScoreInput] = []
        seen: set[str] = set()
        for item in self.dimension_scores:
            dimension_id = resolve_dimension_id(self.role.value, item.dimension)
            if dimension_id is None:
                raise ValueError(
                    f"Unknown dimension for {self.role.value}: {item.dimension}"
                )
            if dimension_id in seen:
                raise ValueError(f"Dimension scored twice: {dimension_id}")
            seen.add(dimension_id)
            resolved.append(item.model_copy(update={"dimension": dimension_id}))
        missing = [dimension for dimension in expected if dimension not in seen]
        if missing:
            raise ValueError(f"Missing dimension scores: {', '.join(missing)}")
        self.dimension_scores = sorted(
            resolved, key=lambda item: expected.index(item.dimension)
        )
        return self


class RevisionItemInput(StrictModel):
    change_type: ChangeType
    source_finding_ids: list[str] = Field(default_factory=list)
    target_sections: list[str] = Field(min_length=1)
    affected_sections: list[str] = Field(default_factory=list)
    issue: str = Field(min_length=1, max_length=1000)
    reason: str = Field(max_length=1000)
    required_change: str = Field(min_length=1, max_length=2000)
    expected_result: str = Field(max_length=1000)
    must_preserve: list[str] = Field(default_factory=list)
    priority: RevisionPriority


class OptimizerOutput(StrictModel):
    objective: str = Field(min_length=1, max_length=1000)
    items: list[RevisionItemInput] = Field(default_factory=list)
    declined_findings: list[DeclinedFinding] = Field(default_factory=list)


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


class RecoveryAction(StrEnum):
    """What the user can do next about a failed run."""

    RETRY = "retry"
    REGENERATE_COMPACT = "regenerate_compact"
    CONTINUE_FROM_BEST = "continue_from_best"
    CHECK_CONFIGURATION = "check_configuration"
    EDIT_INPUT = "edit_input"
    NONE = "none"


class FailureCategory(StrEnum):
    TRANSIENT = "transient"
    """A temporary condition; the same work can succeed later."""
    PERMANENT = "permanent"
    """Configuration or content problem; retrying unchanged will fail again."""
    OUTPUT_LIMIT = "output_limit"
    """The document outgrew the output budget; needs a shorter generation."""
    INTERRUPTED = "interrupted"
    """The service stopped before the run finished; results so far are kept."""


class RunError(StrictModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    retryable: bool = False
    stage: str | None = Field(default=None, max_length=64)
    node: str | None = Field(default=None, max_length=64)
    version: int | None = Field(default=None, ge=1, le=5)
    attempt: int | None = Field(default=None, ge=1)
    recovery_action: RecoveryAction | None = None
    category: FailureCategory | None = None
    trace_id: str | None = Field(default=None, max_length=64)
    occurred_at: datetime | None = None


class IncompleteDraft(StrictModel):
    """A generation that streamed text but never became a version.

    The text itself stays in ``current_prd`` so the reader can see how far it got;
    this record is what stops that text being shown as "正在生成", selected by
    default, downloaded, scored, or compared.
    """

    version: int = Field(ge=1, le=5)
    attempt: int = Field(default=1, ge=1)
    characters: int = Field(default=0, ge=0)
    error_code: str = Field(min_length=1, max_length=100)


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


class QualityIssue(StrictModel):
    code: str = Field(min_length=1, max_length=64)
    severity: str = Field(pattern="^(error|warning|info)$")
    message: str = Field(min_length=1, max_length=600)
    section: str | None = Field(default=None, max_length=200)
    line: int | None = Field(default=None, ge=1)
    excerpt: str | None = Field(default=None, max_length=300)


class PRDQualityReport(StrictModel):
    """Deterministic structure checks on one generated document.

    Advisory: a formatting problem never fails a generation. ``structure_complete``
    is false when a required section is missing, which the UI states plainly.
    """

    characters: int = Field(ge=0)
    sections: int = Field(ge=0)
    tables: int = Field(ge=0)
    list_items: int = Field(ge=0)
    paragraphs: int = Field(ge=0)
    long_paragraphs: int = Field(ge=0)
    longest_paragraph: int = Field(ge=0)
    unlabeled_figures: int = Field(default=0, ge=0)
    structure_complete: bool = True
    missing_sections: list[str] = Field(default_factory=list)
    issues: list[QualityIssue] = Field(default_factory=list)
    budget_characters: int | None = Field(default=None, ge=0)


class PRDVersion(StrictModel):
    version: int = Field(ge=1, le=5)
    content: str
    created_at: datetime
    evaluation: EvaluationResult | None = None
    revision_plan: RevisionPlan | None = None
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    quality: PRDQualityReport | None = None
    generation_mode: GenerationMode | None = None


def utc_now() -> datetime:
    return datetime.now(UTC)


class PRDRunState(StrictModel):
    provider_id: str | None = None
    provider_display_name: str | None = None
    model_id: str | None = None
    model_display_name: str | None = None
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
    trace_id: str | None = Field(default=None, max_length=64)
    """Correlates this run's structured logs. None on runs created before V2."""
    generation_mode: GenerationMode = GenerationMode.STANDARD
    incomplete_draft: IncompleteDraft | None = None
    source_run_id: UUID | None = None
    """Set on a recovery run: the run it was derived from (never modified)."""
    source_version: int | None = Field(default=None, ge=1, le=5)
    recovery_mode: RecoveryMode | None = None
    seed_prd: str | None = None
    """The document the first generation edits, for a continue-from-best run."""
    seed_revision_plan: RevisionPlan | None = None

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
    source_run_id: UUID | None = None


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


class RunHistoryResponse(StrictModel):
    """Every durable event of one run, for replaying a finished run's record."""

    items: list[RunEvent]


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
