"""The four PRD reviewers, the deterministic aggregator, and Finding handling.

Each reviewer is its own model call with its own prompt, rubric and category
list; they run concurrently and none sees another's output. Everything after
the calls is code: evidence checks, domain filtering, severity guards, scores,
cross-reviewer merging, matching against the project's existing findings (so
IDs stay stable and rejected problems stay rejected), and verification of
earlier findings.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

from backend.v3.base import Base, Invalid, NotFound
from backend.v3.document import Documents
from backend.v3.jobs import JobContext
from backend.v3.llm import ReviewerOutput, ReviewFinding
from backend.v3.models import (
    PRD_REVIEWERS,
    SEVERITY_RANK,
    USER_FINDING_STATUSES,
    Finding,
    FindingEvent,
    FindingScope,
    FindingStatus,
    Job,
    JobKind,
    Link,
    PRDSection,
    PRDVersion,
    Reviewer,
    ReviewResult,
    SectionStatus,
    Severity,
    Verification,
    now,
)
from backend.v3.prompts import reviewer_prompt
from backend.v3.rubric import (
    CATEGORIES,
    RUBRIC_VERSION,
    SCORING_VERSION,
    reviewer_score,
)
from backend.v3.rules import evidence_found, guard_severity, same_problem
from backend.v3.store import new_id

MAX_FINDINGS_PER_REVIEWER = 5

#: Earlier findings a reviewer is asked to re-verify.
RECHECK_STATUSES = ("open", "accepted", "modified", "stale", "deferred", "resolved")


class Candidate:
    """One admitted reviewer finding before it is matched to the project."""

    def __init__(
        self,
        reviewer: Reviewer,
        raw: ReviewFinding,
        section: PRDSection | None,
        verified: bool,
    ) -> None:
        self.reviewer = reviewer
        self.reviewers = [reviewer]
        self.raw = raw
        self.section = section
        self.verified = verified
        severity = guard_severity(raw.severity, raw.category, raw.confidence)
        if not verified and severity is Severity.MUST_FIX:
            # Evidence that cannot be found in the document may not block.
            severity = Severity.SHOULD_FIX
        self.severity = severity

    @property
    def section_code(self) -> str | None:
        return self.section.code if self.section else None

    def matches(self, finding: Finding) -> bool:
        return same_problem(
            self.raw.title,
            self.raw.problem,
            self.section_code,
            self.raw.category,
            finding.title,
            finding.problem,
            finding.related_sections[0] if finding.related_sections else None,
            finding.category,
        )


class Reviews(Base):
    def __init__(self, store: Any, jobs: Any, documents: Documents) -> None:
        super().__init__(store, jobs)
        self.documents = documents

    def start_review(self, project_id: str, scope: list[str] | None) -> Job:
        project = self.project(project_id)
        self.ensure_idle(project_id)
        all_sections = self.sections(project_id)
        sections = [s for s in all_sections if s.body.strip()]
        if not sections:
            raise Invalid("DOCUMENT_EMPTY", "There is no document to review yet.")
        unfinished = [s for s in all_sections if s.status is not SectionStatus.DONE]
        if unfinished and not scope:
            # Reviewing half a document produces findings about what is merely
            # not written yet. A scoped recheck of finished sections is fine.
            raise Invalid(
                "DOCUMENT_INCOMPLETE",
                f"{len(unfinished)} sections are not finished yet.",
            )
        codes = {s.code for s in sections}
        scope_codes = [c for c in (scope or []) if c in codes]
        version = self._version_for_review(project_id)
        brief = self._brief_text(project_id)
        base_payload: dict[str, Any] = {
            "sections": [
                {"code": s.code, "num": s.num, "title": s.title, "body": s.body}
                for s in sections
            ],
            "scope": scope_codes,
            "brief": brief or "（审查已有 PRD，没有 Brief）",
        }
        previous = {
            reviewer: [
                {
                    "finding_code": f.code,
                    "title": f.title,
                    "problem": f.problem,
                    "evidence": f.evidence,
                    "status": f.status.value,
                    "section": f.related_sections[0] if f.related_sections else None,
                }
                for f in self.findings(
                    project_id,
                    "scope = 'prd' AND status IN ("
                    + ", ".join("?" for _ in RECHECK_STATUSES)
                    + ")",
                    RECHECK_STATUSES,
                )
                if reviewer in f.reviewers
                and not (
                    f.status is FindingStatus.RESOLVED
                    and f.verification is Verification.RESOLVED
                )
                and (not scope_codes or set(f.related_sections) & set(scope_codes))
            ]
            for reviewer in PRD_REVIEWERS
        }
        version_number = version

        async def call(ctx: JobContext, reviewer: Reviewer) -> ReviewerOutput:
            output = await ctx.structured(
                task=f"review:{reviewer.value}",
                instructions=reviewer_prompt(reviewer),
                payload={**base_payload, "previous_findings": previous[reviewer]},
                schema=ReviewerOutput,
            )
            if output.reviewer is not reviewer:
                raise ValidationError.from_exception_data("ReviewerOutput", [])
            await ctx.emit("reviewer_done", {"reviewer": reviewer.value})
            return output

        async def run(ctx: JobContext) -> dict[str, Any]:
            results = await asyncio.gather(
                *(call(ctx, reviewer) for reviewer in PRD_REVIEWERS),
                return_exceptions=True,
            )
            outputs: dict[Reviewer, ReviewerOutput] = {}
            failed: list[str] = []
            first_error: BaseException | None = None
            for reviewer, result in zip(PRD_REVIEWERS, results, strict=True):
                if isinstance(result, BaseException):
                    if isinstance(result, asyncio.CancelledError):
                        raise result
                    failed.append(reviewer.value)
                    first_error = first_error or result
                    await ctx.emit("reviewer_failed", {"reviewer": reviewer.value})
                else:
                    outputs[reviewer] = result
            if not outputs and first_error is not None:
                raise first_error
            summary = self.aggregate(
                project.id, ctx.job.id, outputs, version_number, scope_codes
            )
            summary["failed_reviewers"] = failed
            return summary

        return self.jobs.start(
            project_id=project_id,
            kind=JobKind.REVIEW,
            input={"scope": scope_codes, "version": version_number},
            runner=run,
        )

    def _version_for_review(self, project_id: str) -> int | None:
        """The version number of the text being reviewed.

        When the sections have changed since the last saved version, they are
        saved first, so a review result always points at what it read.
        """
        latest = self.store.scalar(
            "SELECT MAX(number) FROM v3_versions WHERE project_id = ?", (project_id,)
        )
        sections = self.sections(project_id)
        if latest is not None:
            snapshot = self.store.select(
                PRDVersion,
                "project_id = ? AND number = ?",
                (project_id, int(latest)),
            )[0]
            before = {
                (str(s["code"]), str(s["title"]), str(s["body"]))
                for s in snapshot.sections
            }
            now_ = {(s.code, s.title, s.body) for s in sections}
            if before == now_:
                return int(latest)
        return self.documents.create_version(
            project_id, source="review", actor="系统", note="审查前自动保存"
        ).number

    def _brief_text(self, project_id: str) -> str:
        brief = self.documents.confirmed_brief(project_id)
        if brief is None:
            return "（审查已有 PRD，没有 Brief）"
        clean = self.documents.public_brief(brief)
        return "\n\n".join(f"{s.title}\n{s.text}" for s in clean.sections)

    # --- aggregation ------------------------------------------------------------

    def admit(
        self, reviewer: Reviewer, output: ReviewerOutput, sections: list[PRDSection]
    ) -> tuple[list[Candidate], int]:
        """Keep findings that are in this reviewer's domain and have evidence."""
        bodies = [s.body for s in sections]
        kept: list[Candidate] = []
        filtered = 0
        for raw in output.findings:
            if not raw.evidence.strip():
                filtered += 1
                continue
            if raw.category not in CATEGORIES[reviewer]:
                # Another reviewer's domain: one role never stands in for another.
                filtered += 1
                continue
            section = (
                self.resolve_section(sections[0].project_id, raw.section)
                if sections
                else None
            )
            kept.append(
                Candidate(reviewer, raw, section, evidence_found(raw.evidence, bodies))
            )
        kept.sort(key=lambda c: SEVERITY_RANK[c.severity])
        filtered += max(0, len(kept) - MAX_FINDINGS_PER_REVIEWER)
        return kept[:MAX_FINDINGS_PER_REVIEWER], filtered

    def aggregate(
        self,
        project_id: str,
        job_id: str,
        outputs: dict[Reviewer, ReviewerOutput],
        version: int | None,
        scope: list[str],
    ) -> dict[str, Any]:
        sections = self.sections(project_id)
        admitted: dict[Reviewer, list[Candidate]] = {}
        filtered: dict[Reviewer, int] = {}
        for reviewer, output in outputs.items():
            admitted[reviewer], filtered[reviewer] = self.admit(
                reviewer, output, sections
            )

        # 1. Merge the same problem raised by different reviewers in this round.
        merged: list[Candidate] = []
        for reviewer in PRD_REVIEWERS:
            for candidate in admitted.get(reviewer, []):
                twin = next(
                    (
                        m
                        for m in merged
                        if reviewer not in m.reviewers
                        and same_problem(
                            m.raw.title,
                            m.raw.problem,
                            m.section_code,
                            m.raw.category,
                            candidate.raw.title,
                            candidate.raw.problem,
                            candidate.section_code,
                            candidate.raw.category,
                        )
                    ),
                    None,
                )
                if twin is None:
                    merged.append(candidate)
                    continue
                twin.reviewers.append(reviewer)
                if SEVERITY_RANK[candidate.severity] < SEVERITY_RANK[twin.severity]:
                    twin.severity = candidate.severity

        existing = self.findings(project_id, "scope = 'prd'")
        created: list[str] = []
        updated: list[str] = []
        suppressed: list[str] = []
        codes_by_reviewer: dict[Reviewer, list[str]] = {r: [] for r in outputs}
        with self.store.transaction():
            # 2. Verify earlier findings first, so a resolved one is not reopened
            #    by a reviewer who also confirmed it fixed.
            verified = self._apply_resolutions(project_id, outputs, existing, version)
            # 3. Match each problem to the project's findings for stable IDs.
            for candidate in merged:
                match = next((f for f in existing if candidate.matches(f)), None)
                if match is not None and match.code in verified:
                    match = None if verified[match.code] else match
                    if match is None:
                        continue
                if match is not None:
                    code = self._update_existing(match, candidate, version)
                    if match.status is FindingStatus.REJECTED:
                        suppressed.append(code)
                    else:
                        updated.append(code)
                else:
                    finding = self._create(project_id, candidate, version)
                    existing.append(finding)
                    created.append(finding.code)
                    code = finding.code
                for reviewer in candidate.reviewers:
                    if code not in suppressed:
                        codes_by_reviewer.setdefault(reviewer, []).append(code)
            # 4. One stored result per reviewer, scored by code.
            for reviewer, output in outputs.items():
                kept = admitted[reviewer]
                self.store.insert(
                    ReviewResult(
                        id=new_id(),
                        project_id=project_id,
                        job_id=job_id,
                        reviewer=reviewer,
                        version_number=version,
                        summary=output.summary.strip(),
                        strengths=[s.strip() for s in output.strengths if s.strip()][
                            :3
                        ],
                        risks=[r.strip() for r in output.risks if r.strip()][:3],
                        blocking=any(c.severity is Severity.MUST_FIX for c in kept),
                        dimension_scores=[
                            d.model_dump(mode="json") for d in output.dimension_scores
                        ],
                        score=reviewer_score(reviewer, output.dimension_scores),
                        rubric_version=RUBRIC_VERSION,
                        scoring_version=SCORING_VERSION,
                        finding_codes=codes_by_reviewer.get(reviewer, []),
                        filtered_findings=filtered[reviewer],
                        scope=scope,
                        created_at=now(),
                    )
                )
            for section in sections:
                if section.needs_recheck and (not scope or section.code in scope):
                    section.needs_recheck = False
                    self.store.update(section)
            self.touch(self.project(project_id))
        return {
            "created": created,
            "updated": updated,
            "suppressed": suppressed,
            "verified": sorted(code for code, ok in verified.items() if ok),
            "reviewers": [r.value for r in outputs],
        }

    def _apply_resolutions(
        self,
        project_id: str,
        outputs: dict[Reviewer, ReviewerOutput],
        existing: list[Finding],
        version: int | None,
    ) -> dict[str, bool]:
        by_code = {f.code: f for f in existing}
        verdicts: dict[str, bool] = {}
        for reviewer, output in outputs.items():
            for resolution in output.resolutions:
                finding = by_code.get(resolution.finding_code)
                if finding is None or reviewer not in finding.reviewers:
                    continue
                if finding.status is FindingStatus.REJECTED:
                    continue
                try:
                    verification = Verification(resolution.status)
                except ValueError:
                    continue
                finding.verification = verification
                finding.last_checked_version = version
                if verification is Verification.RESOLVED:
                    verdicts[finding.code] = True
                    if finding.status is not FindingStatus.RESOLVED:
                        self.set_finding_status(
                            finding,
                            FindingStatus.RESOLVED,
                            actor=reviewer.value,
                            note=resolution.note.strip() or "复查确认已解决",
                        )
                        continue
                else:
                    verdicts.setdefault(finding.code, False)
                    if finding.status in (FindingStatus.RESOLVED, FindingStatus.STALE):
                        self.set_finding_status(
                            finding,
                            FindingStatus.OPEN,
                            actor=reviewer.value,
                            note=resolution.note.strip() or "复查发现仍未解决",
                        )
                        continue
                finding.updated_at = now()
                self.store.update(finding)
        return verdicts

    def _create(self, project_id: str, c: Candidate, version: int | None) -> Finding:
        raw = c.raw
        known_items = {i.code for i in self.items(project_id)}
        finding = Finding(
            id=new_id(),
            project_id=project_id,
            code=self.store.next_code(project_id, "FD"),
            scope=FindingScope.PRD,
            reviewer=c.reviewer,
            reviewers=list(c.reviewers),
            kind="review",
            severity=c.severity,
            title=raw.title.strip(),
            category=raw.category,
            section=c.section.num if c.section else (raw.section.strip() or None),
            evidence=raw.evidence.strip(),
            evidence_verified=c.verified,
            problem=raw.problem.strip(),
            cause=raw.cause.strip() or None,
            impact=raw.impact.strip(),
            recommendation=raw.recommendation.strip(),
            confidence=raw.confidence,
            related_items=[code for code in raw.related_items if code in known_items],
            related_sections=[c.section.code] if c.section else [],
            status=FindingStatus.OPEN,
            verification=Verification.NOT_CHECKED,
            first_seen_version=version,
            last_checked_version=version,
            created_at=now(),
            updated_at=now(),
        )
        self.store.insert(finding)
        self.store.insert(
            FindingEvent(
                id=new_id(),
                finding_id=finding.id,
                from_status=None,
                to_status=FindingStatus.OPEN.value,
                actor=c.reviewer.value,
                note="审查发现",
                created_at=now(),
            )
        )
        if c.section:
            self.store.add_link(
                project_id,
                Link(
                    from_code=finding.code,
                    to_code=c.section.code,
                    kind="affects",
                    origin="ai",
                ),
            )
        return finding

    def _update_existing(self, f: Finding, c: Candidate, version: int | None) -> str:
        """Same problem again: keep the ID, history and the user's decision."""
        for reviewer in c.reviewers:
            if reviewer not in f.reviewers:
                f.reviewers.append(reviewer)
        f.last_checked_version = version
        if f.status is FindingStatus.REJECTED:
            f.updated_at = now()
            self.store.update(f)
            return f.code
        f.evidence = c.raw.evidence.strip()
        f.evidence_verified = c.verified
        if SEVERITY_RANK[c.severity] < SEVERITY_RANK[f.severity]:
            f.severity = c.severity
        f.verification = Verification.UNRESOLVED
        if f.status in (FindingStatus.RESOLVED, FindingStatus.STALE):
            self.set_finding_status(
                f, FindingStatus.OPEN, actor=c.reviewer.value, note="复查仍存在"
            )
        else:
            f.updated_at = now()
            self.store.update(f)
        return f.code

    # --- finding handling ---------------------------------------------------------

    def owned_finding(self, finding_id: str) -> Finding:
        finding = self.store.get(Finding, finding_id)
        if finding is None:
            raise NotFound("finding")
        self.project(finding.project_id)
        return finding

    def decide(
        self, finding_id: str, status: FindingStatus, note: str | None
    ) -> Finding:
        finding = self.owned_finding(finding_id)
        if status not in USER_FINDING_STATUSES:
            raise Invalid("STATUS_NOT_ALLOWED", "Resolved and stale are set by checks.")
        if status is FindingStatus.MODIFIED and not (note or "").strip():
            raise Invalid("NOTE_REQUIRED", "Say how you want it changed.")
        if note is not None:
            finding.user_note = note.strip() or None
        self.set_finding_status(finding, status, actor="user", note=note)
        self.touch(self.project(finding.project_id))
        return finding

    def history(self, finding_id: str) -> list[FindingEvent]:
        finding = self.owned_finding(finding_id)
        return self.store.select(
            FindingEvent, "finding_id = ?", (finding.id,), order="created_at"
        )

    def results(self, project_id: str) -> list[ReviewResult]:
        """The latest result of each reviewer."""
        self.project(project_id)
        latest: dict[Reviewer, ReviewResult] = {}
        for result in self.store.select(
            ReviewResult, "project_id = ?", (project_id,), order="created_at"
        ):
            latest[result.reviewer] = result
        return [latest[r] for r in PRD_REVIEWERS if r in latest]
