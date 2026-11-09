"""V3 domain enums and the API shapes built on them."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def now() -> datetime:
    return datetime.now(UTC)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EntryMode(StrEnum):
    IDEA = "idea"
    REQUIREMENT = "requirement"
    REVIEW = "review"


class Depth(StrEnum):
    BRIEF = "brief"
    DETAILED = "detailed"


class Group(StrEnum):
    POSITION = "position"
    GOAL = "goal"
    USER = "user"
    PROBLEM = "problem"
    SCENARIO = "scenario"
    ALTERNATIVE = "alternative"
    SOLUTION = "solution"
    FEATURE = "feature"
    CONSTRAINT = "constraint"
    ASSUMPTION = "assumption"
    DECISION = "decision"
    OPEN = "open"


#: Display order, Chinese label, code prefix, and whether it is P0 core info.
GROUPS: dict[Group, tuple[str, str, bool]] = {
    Group.POSITION: ("产品定位", "POS", True),
    Group.GOAL: ("产品目标", "GOAL", False),
    Group.USER: ("目标用户", "USR", True),
    Group.PROBLEM: ("用户问题", "PRB", True),
    Group.SCENARIO: ("使用场景", "SCN", True),
    Group.ALTERNATIVE: ("现有方案", "ALT", False),
    Group.SOLUTION: ("解决方案", "SOL", False),
    Group.FEATURE: ("功能需求", "FR", False),
    Group.CONSTRAINT: ("业务约束", "CON", False),
    Group.ASSUMPTION: ("假设", "ASM", False),
    Group.DECISION: ("产品决策", "DEC", False),
    Group.OPEN: ("待确认事项", "OPEN", False),
}

CORE_GROUPS: tuple[Group, ...] = tuple(g for g, meta in GROUPS.items() if meta[2])


class ItemStatus(StrEnum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    ASSUMPTION = "assumption"
    PROPOSED = "proposed"
    OPEN = "open"
    REJECTED = "rejected"


#: The statuses a model may assign. Confirmed and rejected are user decisions.
AI_ASSIGNABLE_STATUSES = frozenset(
    {
        ItemStatus.INFERRED,
        ItemStatus.ASSUMPTION,
        ItemStatus.PROPOSED,
        ItemStatus.OPEN,
    }
)


class SourceKind(StrEnum):
    USER = "user"
    AI = "ai"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class QuestionState(StrEnum):
    PENDING = "pending"
    ANSWERED = "answered"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


class SectionOrigin(StrEnum):
    AI = "ai"
    OPTIMIZED = "optimized"
    HUMAN = "human"


class SectionStatus(StrEnum):
    PLANNED = "planned"
    GENERATING = "generating"
    DONE = "done"
    FAILED = "failed"


class FindingScope(StrEnum):
    BASELINE = "baseline"
    PRD = "prd"


class Reviewer(StrEnum):
    ANALYST = "analyst"
    PRODUCT = "product"
    UX = "ux"
    TECH = "tech"
    BIZ = "biz"


PRD_REVIEWERS: tuple[Reviewer, ...] = (
    Reviewer.PRODUCT,
    Reviewer.UX,
    Reviewer.TECH,
    Reviewer.BIZ,
)


class AnalystKind(StrEnum):
    GAP = "gap"
    CONFLICT = "conflict"
    SCENARIO = "scenario"
    RISK = "risk"
    OPPORTUNITY = "opportunity"


class Severity(StrEnum):
    MUST_FIX = "must_fix"
    SHOULD_FIX = "should_fix"
    OPTIONAL = "optional"


SEVERITY_RANK = {Severity.MUST_FIX: 0, Severity.SHOULD_FIX: 1, Severity.OPTIONAL: 2}


class FindingStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    MODIFIED = "modified"
    REJECTED = "rejected"
    DEFERRED = "deferred"
    RESOLVED = "resolved"
    STALE = "stale"


#: Statuses a user may set directly. Resolved and stale come from the system.
USER_FINDING_STATUSES = frozenset(
    {
        FindingStatus.OPEN,
        FindingStatus.ACCEPTED,
        FindingStatus.MODIFIED,
        FindingStatus.REJECTED,
        FindingStatus.DEFERRED,
    }
)

#: Findings still waiting on a user decision or a fix.
UNSETTLED_FINDING_STATUSES = frozenset(
    {
        FindingStatus.OPEN,
        FindingStatus.ACCEPTED,
        FindingStatus.MODIFIED,
        FindingStatus.DEFERRED,
        FindingStatus.STALE,
    }
)


class Verification(StrEnum):
    NOT_CHECKED = "not_checked"
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"


class ChangeType(StrEnum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    REMOVE = "REMOVE"
    CONSOLIDATE = "CONSOLIDATE"
    RETAIN = "RETAIN"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    PARTIAL = "partial"
    DISCARDED = "discarded"


class ChangeState(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    SKIPPED = "skipped"


class JobKind(StrEnum):
    EXPLORE = "explore"
    ANALYZE = "analyze"
    OUTLINE = "outline"
    GENERATE = "generate"
    REVIEW = "review"
    OPTIMIZE = "optimize"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = frozenset(
    {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED}
)


class ChangeClass(StrEnum):
    """How much a section edit can change what the document means."""

    FORMAT = "format"
    DESCRIPTION = "description"
    FEATURE = "feature"
    RULE = "rule"
    POSITIONING = "positioning"
    CONSTRAINT = "constraint"


class Usage(Strict):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class JobError(Strict):
    code: str
    message: str
    retryable: bool = False
    category: str | None = None
    recovery_action: str | None = None
    trace_id: str | None = None


class Job(Strict):
    id: str
    project_id: str
    kind: JobKind
    status: JobStatus
    input: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: JobError | None = None
    provider: str | None = None
    model: str | None = None
    usage: Usage = Field(default_factory=Usage)
    cost: float | None = None
    trace_id: str
    attempts: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    latest_sequence: int = 0


class JobEvent(Strict):
    job_id: str
    sequence: int
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class Project(Strict):
    id: str
    code: str
    name: str
    entry_mode: EntryMode
    depth: Depth
    language: str
    round: int
    doc_title: str = ""
    outline_confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class Message(Strict):
    id: str
    project_id: str
    round: int
    role: str
    """``user`` or ``ai``."""
    kind: str
    """``initial``, ``answer``, ``supplement``, or ``reply``."""
    content: str
    answers: list[dict[str, str]] = Field(default_factory=list)
    """For a user turn: question code, question text, kind, and the answer."""
    changes: list[dict[str, str]] = Field(default_factory=list)
    finding_codes: list[str] = Field(default_factory=list)
    job_id: str | None = None
    created_at: datetime


class Question(Strict):
    id: str
    project_id: str
    code: str
    round: int
    priority: Priority
    text: str
    purpose: str
    target_group: Group
    finding_code: str | None = None
    state: QuestionState
    answer: str | None = None
    created_at: datetime


class RequirementItem(Strict):
    id: str
    project_id: str
    code: str
    group: Group
    content: str
    status: ItemStatus
    source_kind: SourceKind
    source_round: int
    source_quote: str | None = None
    priority: Priority
    reason: str | None = None
    links: list[str] = Field(default_factory=list)
    """Codes of related items, findings, and sections."""
    created_at: datetime
    updated_at: datetime


class ItemRevision(Strict):
    id: str
    item_id: str
    before_content: str | None
    after_content: str
    before_status: ItemStatus | None
    after_status: ItemStatus
    actor: str
    reason: str | None = None
    created_at: datetime


class Link(Strict):
    from_code: str
    to_code: str
    kind: str
    origin: str


class BriefSection(Strict):
    key: str
    title: str
    text: str
    item_codes: list[str] = Field(default_factory=list)
    """Baseline items the section was assembled from. Kept out of ``text``."""
    finding_codes: list[str] = Field(default_factory=list)
    edited: bool = False


class Brief(Strict):
    id: str
    project_id: str
    version: int
    sections: list[BriefSection]
    items: list[dict[str, Any]] = Field(default_factory=list)
    """Frozen copy of the baseline items (code, group, status, content)."""
    unconfirmed_count: int = 0
    confirmed_at: datetime | None = None
    created_at: datetime


class PRDSection(Strict):
    id: str
    project_id: str
    code: str
    position: int
    level: int
    num: str
    title: str
    goal: str = ""
    contents: list[str] = Field(default_factory=list)
    item_codes: list[str] = Field(default_factory=list)
    depends: list[str] = Field(default_factory=list)
    open_points: list[str] = Field(default_factory=list)
    body: str = ""
    origin: SectionOrigin
    status: SectionStatus
    summary: str = ""
    needs_recheck: bool = False
    error: str | None = None
    row_version: int
    updated_at: datetime


class VersionSummary(Strict):
    id: str
    project_id: str
    number: int
    label: str
    source: str
    actor: str
    note: str
    finding_codes: list[str] = Field(default_factory=list)
    section_codes: list[str] = Field(default_factory=list)
    created_at: datetime


class PRDVersion(VersionSummary):
    sections: list[dict[str, Any]] = Field(default_factory=list)


class Finding(Strict):
    id: str
    project_id: str
    code: str
    scope: FindingScope
    reviewer: Reviewer
    reviewers: list[Reviewer] = Field(default_factory=list)
    kind: str
    severity: Severity
    title: str
    category: str = ""
    section: str | None = None
    evidence: str
    evidence_verified: bool = False
    """True when the quote was found in the document or the items exist."""
    problem: str
    cause: str | None = None
    impact: str = ""
    recommendation: str
    confidence: float | None = None
    opportunity: dict[str, Any] | None = None
    related_items: list[str] = Field(default_factory=list)
    related_sections: list[str] = Field(default_factory=list)
    status: FindingStatus
    verification: Verification
    user_note: str | None = None
    first_seen_version: int | None = None
    last_checked_version: int | None = None
    brief_version: int | None = None
    """For analyst findings: the Brief version that was checked, if any."""
    created_at: datetime
    updated_at: datetime


class FindingEvent(Strict):
    id: str
    finding_id: str
    from_status: str | None
    to_status: str
    actor: str
    note: str | None = None
    created_at: datetime


class ReviewResult(Strict):
    id: str
    project_id: str
    job_id: str
    reviewer: Reviewer
    version_number: int | None
    summary: str
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    blocking: bool = False
    dimension_scores: list[dict[str, Any]] = Field(default_factory=list)
    score: int | None = None
    rubric_version: str
    scoring_version: str
    finding_codes: list[str] = Field(default_factory=list)
    filtered_findings: int = 0
    scope: list[str] = Field(default_factory=list)
    created_at: datetime


class ProposalChange(Strict):
    id: str
    proposal_id: str
    position: int = 0
    change_type: ChangeType
    section_code: str
    new_title: str | None = None
    reason: str
    before: str
    after: str
    finding_codes: list[str] = Field(default_factory=list)
    affected_sections: list[str] = Field(default_factory=list)
    must_preserve: list[str] = Field(default_factory=list)
    human_section: bool = False
    base_row_version: int = 0
    warnings: list[str] = Field(default_factory=list)
    state: ChangeState


class Proposal(Strict):
    id: str
    project_id: str
    code: str
    job_id: str
    status: ProposalStatus
    objective: str
    declined: list[dict[str, str]] = Field(default_factory=list)
    changes: list[ProposalChange] = Field(default_factory=list)
    created_at: datetime
