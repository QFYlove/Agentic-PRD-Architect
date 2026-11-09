"""Deterministic review processing: scores, the gate, dedup, and traceability.

The models judge; this module computes. A reviewer supplies 1-5 dimension scores
with reasons and a list of findings. Everything numeric that a reader or the gate
relies on -- the role score, the overall score, the gate status, how many
blockers are open, which findings were merged, which were resolved -- is derived
here from that input, so it can be recomputed and can never be set by a model.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from backend.rubric import (
    DIMENSION_SCORE_MAX,
    RUBRIC_VERSION,
    SCORING_VERSION,
    dimensions_for,
)
from backend.schemas import (
    SEVERITY_ORDER,
    DimensionScore,
    DimensionScoreInput,
    EvaluationResult,
    FeedbackItem,
    FeedbackSeverity,
    FindingCategory,
    FindingObservation,
    FindingResolution,
    FindingStatus,
    GateStatus,
    OptimizerOutput,
    ReviewerOutput,
    ReviewRole,
    RevisionItem,
    RevisionPlan,
    RevisionPriority,
    RevisionSource,
    RoleReview,
)

#: Formal findings kept per reviewer. Beyond this a review stops being a list of
#: the problems that matter and becomes the 24-item wall run 9fa59292 produced.
MAX_FINDINGS_PER_ROLE = 5
MAX_STRENGTHS_PER_ROLE = 3
MAX_SUMMARY_SENTENCES = 2
MAX_SUMMARY_CHARACTERS = 300

#: A `must_fix` the reviewer itself is unsure of is not allowed to block a run.
MIN_BLOCKING_CONFIDENCE = 0.5

ROLE_ORDER: tuple[ReviewRole, ...] = (ReviewRole.TECH, ReviewRole.UX, ReviewRole.BIZ)


def _round_half_up(value: Decimal, places: str = "1") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def role_score(role: str, dimension_scores: Sequence[DimensionScoreInput]) -> int:
    """``Σ(score / 5 × weight) × 100``, rounded half-up to an integer."""
    by_id = {item.dimension: item.score for item in dimension_scores}
    total = Decimal(0)
    for dimension in dimensions_for(role):
        if dimension.id not in by_id:
            raise ValueError(f"Missing dimension score: {dimension.id}")
        total += (
            Decimal(by_id[dimension.id])
            / Decimal(DIMENSION_SCORE_MAX)
            * Decimal(str(dimension.weight))
        )
    return int(_round_half_up(total * 100))


def overall_score(tech: int, ux: int, biz: int) -> float:
    """Equal-weight mean of the three role scores, one decimal, half-up."""
    mean = Decimal(tech + ux + biz) / Decimal(3)
    return float(_round_half_up(mean, "0.1"))


def _summary(text: str) -> str:
    sentences = re.findall(r"[^。！？!?.]+[。！？!?.]?", text.strip())
    kept = "".join(sentences[:MAX_SUMMARY_SENTENCES]).strip() or text.strip()
    if len(kept) > MAX_SUMMARY_CHARACTERS:
        kept = kept[: MAX_SUMMARY_CHARACTERS - 1].rstrip() + "…"
    return kept


def _severity_rank(severity: FeedbackSeverity) -> int:
    return SEVERITY_ORDER.index(severity)


def _guard_severity(
    severity: FeedbackSeverity,
    category: FindingCategory,
    confidence: float | None,
) -> FeedbackSeverity:
    """Lower a `must_fix` the rubric does not allow.

    Two cases, both seen in real reviews: a blocker whose only content is "this
    should be quantified" (the rubric excludes it explicitly), and a blocker the
    reviewer marked low-confidence. Neither may hold a run on its own.
    """
    if severity is not FeedbackSeverity.MUST_FIX:
        return severity
    if category is FindingCategory.QUANTIFICATION:
        return FeedbackSeverity.SHOULD_FIX
    if confidence is not None and confidence < MIN_BLOCKING_CONFIDENCE:
        return FeedbackSeverity.SHOULD_FIX
    return severity


def normalize_review(
    output: ReviewerOutput,
    *,
    version: int,
    previous_finding_ids: Iterable[str] = (),
) -> RoleReview:
    """Turn a reviewer's raw output into the stored, scored review."""
    role = output.role
    kept: list[tuple[int, FeedbackItem]] = []
    filtered = 0
    for index, finding in enumerate(output.findings):
        evidence = finding.evidence.strip()
        if not evidence:
            # A finding nobody can locate in the document is an opinion, not a
            # problem the user can act on.
            filtered += 1
            continue
        severity = _guard_severity(
            finding.severity, finding.category, finding.confidence
        )
        kept.append(
            (
                index,
                FeedbackItem(
                    severity=severity,
                    issue=finding.problem.strip(),
                    recommendation=finding.recommendation.strip(),
                    title=finding.title.strip(),
                    category=finding.category,
                    section=finding.section.strip() or None,
                    evidence=evidence,
                    user_impact=finding.user_impact.strip() or None,
                    source_role=role,
                    source_roles=[role],
                    confidence=finding.confidence,
                    severity_adjusted_from=(
                        finding.severity if severity is not finding.severity else None
                    ),
                ),
            )
        )
    kept.sort(key=lambda pair: (_severity_rank(pair[1].severity), pair[0]))
    filtered += max(0, len(kept) - MAX_FINDINGS_PER_ROLE)
    feedback = [
        item.model_copy(update={"finding_id": f"v{version}-{role.value}-{number}"})
        for number, (_, item) in enumerate(kept[:MAX_FINDINGS_PER_ROLE], start=1)
    ]
    weights = {dimension.id: dimension.weight for dimension in dimensions_for(role)}
    allowed = set(previous_finding_ids)
    return RoleReview(
        role=role,
        score=role_score(role.value, output.dimension_scores),
        summary=_summary(output.summary),
        strengths=[item.strip() for item in output.strengths if item.strip()][
            :MAX_STRENGTHS_PER_ROLE
        ],
        feedback=feedback,
        dimension_scores=[
            DimensionScore(
                dimension=item.dimension,
                score=item.score,
                rationale=item.rationale.strip(),
                weight=weights[item.dimension],
            )
            for item in output.dimension_scores
        ],
        rubric_version=RUBRIC_VERSION,
        scoring_version=SCORING_VERSION,
        filtered_findings=filtered,
        resolutions=[
            FindingResolution(
                finding_id=item.finding_id,
                status=item.status,
                note=item.note.strip() or None,
            )
            for item in output.resolutions
            if item.finding_id in allowed
        ],
    )


# --- Aggregation ----------------------------------------------------------

_PUNCTUATION = re.compile(r"[\s\W_]+", re.UNICODE)
_SECTION_NUMBER = re.compile(r"\d+(?:\.\d+)*")


def _normalize(text: str | None) -> str:
    return _PUNCTUATION.sub("", (text or "").casefold())


def section_key(section: str | None) -> str:
    """`5.5 配额与限制`, `§5.5` and `5.5` are one section; `5.5` and `5.6` are not."""
    if not section:
        return ""
    number = _SECTION_NUMBER.search(section)
    if number:
        return number.group(0)
    return _normalize(section)


def _bigrams(text: str) -> set[str]:
    normalized = _normalize(text)
    if len(normalized) < 2:
        return {normalized} if normalized else set()
    return {normalized[index : index + 2] for index in range(len(normalized) - 1)}


def text_overlap(left: str, right: str) -> float:
    """Overlap coefficient on character bigrams -- works for CJK and English."""
    a, b = _bigrams(left), _bigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def is_same_problem(left: FeedbackItem, right: FeedbackItem) -> bool:
    """Conservative: only merge what is clearly one problem raised by two roles.

    Merging two different problems hides one of them from the optimizer, which
    is worse than showing a near-duplicate, so both rules require strong overlap.
    Same section *and* similar titles, or near-identical wording in the same
    category. A semantic paraphrase in a different section is left for the
    optimizer, which can cite several finding ids in one plan item.
    """
    if left.source_role is not None and left.source_role == right.source_role:
        # One reviewer's list is already de-duplicated by that reviewer; two of
        # its own findings are two problems even when they read alike.
        return False
    left_title = left.title or left.issue
    right_title = right.title or right.issue
    same_section = bool(section_key(left.section)) and section_key(
        left.section
    ) == section_key(right.section)
    if same_section and text_overlap(left_title, right_title) >= 0.5:
        return True
    same_category = left.category is not None and left.category == right.category
    return (
        same_category
        and text_overlap(f"{left_title}{left.issue}", f"{right_title}{right.issue}")
        >= 0.75
    )


def _observation(item: FeedbackItem) -> FindingObservation | None:
    if item.finding_id is None or item.source_role is None:
        return None
    return FindingObservation(
        finding_id=item.finding_id,
        role=item.source_role,
        severity=item.severity,
        problem=item.issue,
        evidence=item.evidence,
    )


def deduplicate(findings: Sequence[FeedbackItem]) -> list[FeedbackItem]:
    """Merge findings that describe one problem, keeping every reviewer's view."""
    ordered = sorted(
        enumerate(findings),
        key=lambda pair: (_severity_rank(pair[1].severity), pair[0]),
    )
    clusters: list[list[FeedbackItem]] = []
    for _, item in ordered:
        for cluster in clusters:
            if any(is_same_problem(member, item) for member in cluster):
                cluster.append(item)
                break
        else:
            clusters.append([item])
    merged: list[FeedbackItem] = []
    for cluster in clusters:
        primary = cluster[0]
        if len(cluster) == 1:
            merged.append(primary)
            continue
        roles = {role for member in cluster for role in member.source_roles}
        if primary.source_role is not None:
            roles.add(primary.source_role)
        for member in cluster:
            if member.source_role is not None:
                roles.add(member.source_role)
        observations = [
            observation
            for member in cluster
            if (observation := _observation(member)) is not None
        ]
        merged.append(
            primary.model_copy(
                update={
                    "source_roles": [role for role in ROLE_ORDER if role in roles],
                    "merged_from": [
                        member.finding_id
                        for member in cluster[1:]
                        if member.finding_id is not None
                    ],
                    "observations": observations,
                }
            )
        )
    return merged


@dataclass(frozen=True)
class GateResult:
    threshold_met: bool
    must_fix_count: int
    passed: bool
    status: GateStatus


def evaluate_gate(
    evaluation: EvaluationResult | None, quality_threshold: float
) -> GateResult:
    """Both halves of the gate, and which non-pass state the run is in.

    ``UNSCORED`` is the honest answer when there is no evaluation to judge -- a
    version that never finished, or one whose reviews did not arrive. It is never
    computed from partial data.
    """
    if evaluation is None:
        return GateResult(False, 0, False, GateStatus.UNSCORED)
    blockers = [
        item
        for item in evaluation.combined_feedback
        if item.severity is FeedbackSeverity.MUST_FIX
    ]
    threshold_met = evaluation.overall_score >= quality_threshold
    passed = threshold_met and not blockers
    if passed:
        status = GateStatus.PASSED
    elif any(
        item.category is FindingCategory.CONSTRAINT_VIOLATION for item in blockers
    ):
        status = GateStatus.BLOCKED
    else:
        status = GateStatus.NEEDS_REVISION
    return GateResult(threshold_met, len(blockers), passed, status)


def build_evaluation(
    tech: RoleReview,
    ux: RoleReview,
    biz: RoleReview,
    *,
    quality_threshold: float,
    previous: EvaluationResult | None = None,
    previous_plan: RevisionPlan | None = None,
) -> tuple[EvaluationResult, GateResult]:
    raw = [*tech.feedback, *ux.feedback, *biz.feedback]
    combined = deduplicate(raw)
    scored = all(not review.is_legacy_scoring for review in (tech, ux, biz))
    evaluation = EvaluationResult(
        tech=tech,
        ux=ux,
        biz=biz,
        overall_score=overall_score(tech.score, ux.score, biz.score),
        combined_feedback=combined,
        findings_before_dedup=len(raw),
        rubric_version=RUBRIC_VERSION if scored else None,
        scoring_version=SCORING_VERSION if scored else None,
        finding_resolutions=resolve_previous_findings(
            previous, previous_plan, (tech, ux, biz)
        ),
    )
    gate = evaluate_gate(evaluation, quality_threshold)
    return evaluation.model_copy(update={"gate_status": gate.status}), gate


_STATUS_RANK = {
    FindingStatus.UNRESOLVED: 0,
    FindingStatus.PARTIALLY_RESOLVED: 1,
    FindingStatus.RESOLVED: 2,
}


def resolve_previous_findings(
    previous: EvaluationResult | None,
    plan: RevisionPlan | None,
    reviews: Sequence[RoleReview],
) -> list[FindingResolution]:
    """Status of every finding from the previous version, in this version.

    Declined by the optimizer wins (the finding was knowingly not acted on).
    Otherwise every reviewer that raised the finding re-checks it, and the least
    resolved verdict stands: one reviewer still seeing the problem means it is
    not closed. A finding nobody re-checked is reported as such, never as fixed.
    """
    if previous is None:
        return []
    declined = {
        item.finding_id: item.reason
        for item in (plan.declined_findings if plan else [])
    }
    verdicts: dict[str, list[FindingResolution]] = {}
    for review in reviews:
        for resolution in review.resolutions:
            verdicts.setdefault(resolution.finding_id, []).append(resolution)
    results: list[FindingResolution] = []
    for finding in previous.combined_feedback:
        if finding.finding_id is None:
            continue
        common = {
            "finding_id": finding.finding_id,
            "title": finding.title or finding.issue[:200],
            "severity": finding.severity,
            "source_version": _version_of(finding.finding_id),
        }
        if finding.finding_id in declined:
            results.append(
                FindingResolution(
                    status=FindingStatus.DECLINED,
                    note=declined[finding.finding_id][:600],
                    **common,
                )
            )
            continue
        checked = [
            verdict
            for verdict in verdicts.get(finding.finding_id, [])
            if verdict.status in _STATUS_RANK
        ]
        if not checked:
            results.append(
                FindingResolution(status=FindingStatus.NOT_CHECKED, **common)
            )
            continue
        worst = min(checked, key=lambda verdict: _STATUS_RANK[verdict.status])
        results.append(
            FindingResolution(status=worst.status, note=worst.note, **common)
        )
    return results


def _version_of(finding_id: str) -> int | None:
    match = re.match(r"v(\d+)-", finding_id)
    if match is None:
        return None
    value = int(match.group(1))
    return value if 1 <= value <= 5 else None


# --- Revision plans -------------------------------------------------------

_USER_REFERENCES = {"user", "user_override", "用户", "用户补充"}

_SEVERITY_PRIORITY = {
    FeedbackSeverity.MUST_FIX: RevisionPriority.HIGH,
    FeedbackSeverity.SHOULD_FIX: RevisionPriority.MEDIUM,
    FeedbackSeverity.OPTIONAL: RevisionPriority.LOW,
}


def _roles_of(finding: FeedbackItem) -> list[ReviewRole]:
    if finding.source_roles:
        return list(finding.source_roles)
    return [finding.source_role] if finding.source_role is not None else []


def _finding_index(findings: Sequence[FeedbackItem]) -> dict[str, FeedbackItem]:
    index: dict[str, FeedbackItem] = {}
    for finding in findings:
        if finding.finding_id is None:
            continue
        index[finding.finding_id] = finding
        for merged in finding.merged_from:
            index.setdefault(merged, finding)
    return index


def build_revision_plan(
    output: OptimizerOutput,
    *,
    iteration: int,
    findings: Sequence[FeedbackItem],
    user_override: str | None,
) -> RevisionPlan:
    """Turn the optimizer's output into a stored plan with traceable sources.

    Source roles come from the referenced finding ids, never from the model. An
    id the optimizer invented is dropped. A `must_fix` the optimizer neither
    planned nor explicitly declined gets an item of its own: a blocker cannot
    silently fall out of the loop.
    """
    index = _finding_index(findings)
    items: list[RevisionItem] = []
    referenced: set[str] = set()
    for number, item in enumerate(output.items, start=1):
        finding_ids: list[str] = []
        is_user = False
        for raw_id in item.source_finding_ids:
            key = raw_id.strip()
            if key.casefold() in _USER_REFERENCES:
                is_user = True
                continue
            finding = index.get(key)
            if finding is not None and finding.finding_id is not None:
                if finding.finding_id not in finding_ids:
                    finding_ids.append(finding.finding_id)
        sources: list[RevisionSource] = []
        for finding_id in finding_ids:
            for role in _roles_of(index[finding_id]):
                source = RevisionSource(role.value)
                if source not in sources:
                    sources.append(source)
        if is_user and user_override:
            sources.insert(0, RevisionSource.USER)
        if not sources:
            sources = [RevisionSource.OPTIMIZER]
        priority = item.priority
        if is_user and user_override:
            priority = RevisionPriority.HIGH
        if any(
            index[finding_id].severity is FeedbackSeverity.MUST_FIX
            for finding_id in finding_ids
        ):
            priority = RevisionPriority.HIGH
        targets = [
            section.strip() for section in item.target_sections if section.strip()
        ]
        referenced.update(finding_ids)
        items.append(
            RevisionItem(
                item_id=f"p{iteration}-{number}",
                source_role=sources[0],
                source_roles=sources,
                issue=item.issue.strip(),
                required_change=item.required_change.strip(),
                target_section=" / ".join(targets)[:500] or "—",
                target_sections=targets,
                affected_sections=[
                    section.strip()
                    for section in item.affected_sections
                    if section.strip() and section.strip() not in targets
                ],
                priority=priority,
                change_type=item.change_type,
                source_finding_ids=finding_ids,
                reason=item.reason.strip() or None,
                expected_result=item.expected_result.strip() or None,
                must_preserve=[
                    value.strip() for value in item.must_preserve if value.strip()
                ],
            )
        )
    declined = [
        entry.model_copy(update={"finding_id": index[entry.finding_id].finding_id})
        for entry in output.declined_findings
        if entry.finding_id in index and index[entry.finding_id].finding_id is not None
    ]
    declined_ids = {entry.finding_id for entry in declined}
    for finding in findings:
        if (
            finding.severity is FeedbackSeverity.MUST_FIX
            and finding.finding_id is not None
            and finding.finding_id not in referenced
            and finding.finding_id not in declined_ids
        ):
            roles = [
                RevisionSource(role.value) for role in (finding.source_roles or [])
            ] or [RevisionSource.OPTIMIZER]
            target = finding.section or "—"
            items.append(
                RevisionItem(
                    item_id=f"p{iteration}-{len(items) + 1}",
                    source_role=roles[0],
                    source_roles=roles,
                    issue=finding.title or finding.issue[:1000],
                    required_change=finding.recommendation,
                    target_section=target[:500],
                    target_sections=[target] if finding.section else [],
                    priority=RevisionPriority.HIGH,
                    change_type=None,
                    source_finding_ids=[finding.finding_id],
                    reason="必须修复的问题未被修订计划覆盖，已自动补入。",
                )
            )
    if user_override and not any(
        RevisionSource.USER in item.source_roles for item in items
    ):
        items.append(
            RevisionItem(
                item_id=f"p{iteration}-{len(items) + 1}",
                source_role=RevisionSource.USER,
                source_roles=[RevisionSource.USER],
                issue="用户补充的优化要求",
                required_change=user_override,
                target_section="—",
                priority=RevisionPriority.HIGH,
            )
        )
    return RevisionPlan(
        iteration=iteration,
        objective=output.objective.strip(),
        items=items,
        user_override=user_override,
        declined_findings=declined,
        plan_version="v2",
    )


def severity_priority(severity: FeedbackSeverity) -> RevisionPriority:
    return _SEVERITY_PRIORITY[severity]
