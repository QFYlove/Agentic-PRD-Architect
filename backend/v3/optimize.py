"""Targeted optimisation: proposals for accepted findings, applied by the user.

The Optimizer only ever sees findings the user accepted (or accepted with
changes). Its output is stored as a proposal and changes nothing; applying a
proposal is an ordinary user action that checks each section's row version, so
an edit made in the meantime is never overwritten.
"""

from __future__ import annotations

from typing import Any

from backend.v3.base import Base, Conflict, Invalid, NotFound
from backend.v3.document import Documents
from backend.v3.jobs import JobContext
from backend.v3.llm import OptimizerOutput
from backend.v3.models import (
    ChangeClass,
    ChangeState,
    ChangeType,
    Finding,
    FindingStatus,
    Job,
    JobKind,
    PRDSection,
    Proposal,
    ProposalChange,
    ProposalStatus,
    SectionOrigin,
    SectionStatus,
    now,
)
from backend.v3.prompts import OPTIMIZER_PROMPT
from backend.v3.rules import classify_change, compact, strip_internal_refs, summarize
from backend.v3.store import new_id

OPTIMIZABLE = (FindingStatus.ACCEPTED, FindingStatus.MODIFIED)


class Optimizer(Base):
    def __init__(self, store: Any, jobs: Any, documents: Documents) -> None:
        super().__init__(store, jobs)
        self.documents = documents

    def accepted_findings(self, project_id: str) -> list[Finding]:
        return [
            f
            for f in self.findings(project_id, "scope = 'prd'")
            if f.status in OPTIMIZABLE
        ]

    def start_optimize(self, project_id: str) -> Job:
        self.project(project_id)
        self.ensure_idle(project_id)
        findings = self.accepted_findings(project_id)
        if not findings:
            raise Invalid(
                "NOTHING_ACCEPTED", "Accept at least one finding before optimising."
            )
        sections = self.sections(project_id)
        wanted = {code for f in findings for code in f.related_sections}
        nums = {s.num for s in sections if s.code in wanted}
        relevant = [
            s
            for s in sections
            if s.code in wanted or set(s.depends) & nums or not wanted
        ]
        payload = {
            "findings": [
                {
                    "finding_code": f.code,
                    "title": f.title,
                    "problem": f.problem,
                    "recommendation": f.recommendation,
                    "user_note": f.user_note,
                    "sections": f.related_sections,
                    "evidence": f.evidence,
                }
                for f in findings
            ],
            "sections": [
                {
                    "code": s.code,
                    "num": s.num,
                    "title": s.title,
                    "body": s.body,
                    "human": s.origin is SectionOrigin.HUMAN,
                }
                for s in relevant
            ],
            "outline": [
                {"code": s.code, "num": s.num, "title": s.title} for s in sections
            ],
        }
        allowed = {f.code for f in findings}

        async def run(ctx: JobContext) -> dict[str, Any]:
            output = await ctx.structured(
                task="optimize",
                instructions=OPTIMIZER_PROMPT,
                payload=payload,
                schema=OptimizerOutput,
            )
            proposal = self.store_proposal(project_id, ctx.job.id, output, allowed)
            return {"proposal": proposal.code, "changes": len(proposal.changes)}

        return self.jobs.start(
            project_id=project_id,
            kind=JobKind.OPTIMIZE,
            input={"findings": sorted(allowed)},
            runner=run,
        )

    def store_proposal(
        self, project_id: str, job_id: str, output: OptimizerOutput, allowed: set[str]
    ) -> Proposal:
        """Keep only changes that cite an accepted finding and a real section."""
        proposal = Proposal(
            id=new_id(),
            project_id=project_id,
            code=self.store.next_code(project_id, "PR"),
            job_id=job_id,
            status=ProposalStatus.PENDING,
            objective=output.objective.strip(),
            declined=[
                {"finding_code": d.finding_code, "reason": d.reason}
                for d in output.declined
                if d.finding_code in allowed
            ],
            created_at=now(),
        )
        changes: list[ProposalChange] = []
        internal = self.internal_codes(project_id)
        for position, raw in enumerate(output.changes):
            codes = [code for code in raw.finding_codes if code in allowed]
            if not codes:
                continue
            section = self.resolve_section(project_id, raw.section)
            if section is None:
                continue
            if raw.change_type in (
                ChangeType.UPDATE,
                ChangeType.CONSOLIDATE,
                ChangeType.ADD,
            ):
                if not raw.after.strip():
                    continue
            if raw.change_type is ChangeType.ADD and not (raw.new_title or "").strip():
                continue
            before = "" if raw.change_type is ChangeType.ADD else section.body
            after = (
                ""
                if raw.change_type is ChangeType.REMOVE
                else strip_internal_refs(raw.after.strip(), internal)
            )
            if raw.change_type is ChangeType.RETAIN:
                after = section.body
            warnings = [
                phrase
                for phrase in raw.must_preserve
                if raw.change_type is not ChangeType.REMOVE
                and compact(phrase) not in compact(after)
            ]
            changes.append(
                ProposalChange(
                    id=new_id(),
                    proposal_id=proposal.id,
                    position=position,
                    change_type=raw.change_type,
                    section_code=section.code,
                    new_title=(raw.new_title or "").strip() or None,
                    reason=raw.reason.strip(),
                    before=before,
                    after=after,
                    finding_codes=codes,
                    affected_sections=[
                        s.code
                        for ref in raw.affected_sections
                        if (s := self.resolve_section(project_id, ref)) is not None
                    ],
                    must_preserve=raw.must_preserve,
                    human_section=section.origin is SectionOrigin.HUMAN,
                    base_row_version=section.row_version,
                    warnings=warnings,
                    state=(
                        ChangeState.SKIPPED
                        if raw.change_type is ChangeType.RETAIN
                        else ChangeState.PENDING
                    ),
                )
            )
        proposal.changes = changes
        with self.store.transaction():
            self.store.insert(proposal)
            for change in changes:
                self.store.insert(change)
        return proposal

    # --- proposals --------------------------------------------------------------

    def proposal(self, proposal_id: str) -> Proposal:
        proposal = self.store.get(Proposal, proposal_id)
        if proposal is None:
            raise NotFound("proposal")
        self.project(proposal.project_id)
        proposal.changes = self.store.select(
            ProposalChange, "proposal_id = ?", (proposal.id,), order="position"
        )
        return proposal

    def proposals(self, project_id: str) -> list[Proposal]:
        self.project(project_id)
        rows = self.store.select(
            Proposal, "project_id = ?", (project_id,), order="created_at DESC"
        )
        return [self.proposal(p.id) for p in rows]

    def discard(self, proposal_id: str) -> Proposal:
        proposal = self.proposal(proposal_id)
        if proposal.status is not ProposalStatus.PENDING:
            raise Conflict("PROPOSAL_CLOSED", "This proposal was already handled.")
        proposal.status = ProposalStatus.DISCARDED
        self.store.update(proposal)
        return proposal

    def apply(self, proposal_id: str, change_ids: list[str] | None) -> dict[str, Any]:
        """Apply the chosen changes. Each one is checked against its section's
        row version; a section edited since the proposal is skipped, not
        overwritten."""
        proposal = self.proposal(proposal_id)
        if proposal.status is not ProposalStatus.PENDING:
            raise Conflict("PROPOSAL_CLOSED", "This proposal was already handled.")
        project_id = proposal.project_id
        pending = [c for c in proposal.changes if c.state is ChangeState.PENDING]
        chosen = (
            pending
            if change_ids is None
            else [c for c in pending if c.id in set(change_ids)]
        )
        if not chosen:
            raise Invalid("NOTHING_CHOSEN", "Choose at least one change to apply.")
        applied: list[ProposalChange] = []
        conflicts: list[str] = []
        touched: list[tuple[PRDSection, ChangeClass]] = []
        with self.store.transaction():
            for change in chosen:
                section = self.section_by_code(project_id, change.section_code)
                if section is None or section.row_version != change.base_row_version:
                    conflicts.append(change.id)
                    continue
                if change.change_type is ChangeType.REMOVE:
                    self.store.delete(PRDSection, "id = ?", (section.id,))
                elif change.change_type is ChangeType.ADD:
                    added = self.documents.add_section(
                        project_id,
                        title=change.new_title or "新章节",
                        after=section.code,
                        level=section.level,
                    )
                    added.body = change.after
                    added.summary = summarize(change.after)
                    added.status = SectionStatus.DONE
                    added.origin = SectionOrigin.OPTIMIZED
                    added.row_version += 1
                    self.store.update(added)
                else:
                    kind = classify_change(section.title, section.body, change.after)
                    section.body = change.after
                    section.summary = summarize(change.after)
                    if section.origin is not SectionOrigin.HUMAN:
                        section.origin = SectionOrigin.OPTIMIZED
                    section.row_version += 1
                    section.updated_at = now()
                    self.store.update(section)
                    touched.append((section, kind))
                change.state = ChangeState.APPLIED
                self.store.update(change)
                applied.append(change)
            if applied:
                self.documents._renumber(self.sections(project_id))
            fixed = sorted({code for c in applied for code in c.finding_codes})
            for code in fixed:
                finding = self.finding_by_code(project_id, code)
                if finding is not None and finding.status in OPTIMIZABLE:
                    self.set_finding_status(
                        finding,
                        FindingStatus.RESOLVED,
                        actor="user",
                        note=f"已应用修改提案 {proposal.code}，等待复查确认",
                    )
            impact: dict[str, list[str]] = {"sections": [], "stale": []}
            for touched_section, kind in touched:
                current = self.section_by_code(project_id, touched_section.code)
                if current is None:
                    continue
                result = self.documents.impact_of(current, kind)
                impact["sections"] += result["sections"]
                impact["stale"] += result["stale"]
                current.needs_recheck = True
                self.store.update(current)
            applied_ids = {c.id for c in applied}
            remaining = [
                c
                for c in proposal.changes
                if c.state is ChangeState.PENDING and c.id not in applied_ids
            ]
            proposal.status = (
                ProposalStatus.APPLIED
                if applied and not remaining and not conflicts
                else ProposalStatus.PARTIAL
                if applied
                else ProposalStatus.PENDING
            )
            self.store.update(proposal)
            version = None
            if applied:
                version = self.documents.create_version(
                    project_id,
                    source="ai_optimize",
                    actor="AI 优化（你确认）",
                    note=f"按 {proposal.code} 修改：{proposal.objective}"[:200],
                    finding_codes=fixed,
                ).number
        return {
            "applied": [c.id for c in applied],
            "conflicts": conflicts,
            "findings": fixed,
            "impact": impact,
            "version": version,
        }
