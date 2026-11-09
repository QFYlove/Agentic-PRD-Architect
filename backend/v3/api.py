"""``/api/v3`` routes. Handlers validate input and delegate to the services."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import Field
from sse_starlette.sse import EventSourceResponse

from backend.errors import AppError
from backend.v3.base import Base
from backend.v3.document import Documents
from backend.v3.explore import Requirements
from backend.v3.jobs import JobManager
from backend.v3.models import (
    GROUPS,
    Depth,
    EntryMode,
    FindingStatus,
    Group,
    ItemStatus,
    Job,
    Priority,
    Project,
    QuestionState,
    Reviewer,
    Strict,
)
from backend.v3.optimize import Optimizer
from backend.v3.quality import Quality, blocking
from backend.v3.review import Reviews
from backend.v3.rubric import rubric_document
from backend.v3.store import ProjectStore


class CreateProject(Strict):
    text: str = Field(min_length=1, max_length=20_000)
    entry_mode: EntryMode = EntryMode.IDEA
    name: str | None = Field(default=None, max_length=60)
    depth: Depth = Depth.DETAILED


class RenameProject(Strict):
    name: str = Field(min_length=1, max_length=60)


class TurnAnswer(Strict):
    question: str
    kind: str = Field(pattern="^(answer|skip|unknown)$")
    text: str = Field(default="", max_length=4000)


class SubmitTurn(Strict):
    answers: list[TurnAnswer] = Field(default_factory=list, max_length=5)
    supplement: str = Field(default="", max_length=8000)
    depth: Depth | None = None


class AddItem(Strict):
    group: Group
    content: str = Field(min_length=1, max_length=600)
    priority: Priority = Priority.P1


class PatchItem(Strict):
    content: str | None = Field(default=None, max_length=600)
    status: ItemStatus | None = None
    group: Group | None = None
    priority: Priority | None = None
    reason: str | None = Field(default=None, max_length=400)


class Analyze(Strict):
    brief_id: str | None = None


class EditBrief(Strict):
    key: str
    text: str = Field(max_length=8000)


class AddSection(Strict):
    title: str = Field(min_length=1, max_length=80)
    after: str | None = None
    level: int = Field(default=1, ge=1, le=2)


class OrderEntry(Strict):
    code: str
    level: int = Field(ge=1, le=2)


class Reorder(Strict):
    order: list[OrderEntry]


class SaveSection(Strict):
    row_version: int
    body: str | None = Field(default=None, max_length=60_000)
    title: str | None = Field(default=None, max_length=80)


class DeleteSection(Strict):
    row_version: int


class Generate(Strict):
    sections: list[str] | None = None


class StartReview(Strict):
    sections: list[str] | None = None


class Decide(Strict):
    status: FindingStatus
    note: str | None = Field(default=None, max_length=2000)


class ApplyProposal(Strict):
    changes: list[str] | None = None


class SaveVersion(Strict):
    note: str = Field(default="", max_length=200)


class ImportPRD(Strict):
    text: str = Field(min_length=1, max_length=200_000)


def job_view(job: Job) -> dict[str, Any]:
    data = job.model_dump(mode="json", exclude={"input"})
    data["events_url"] = f"/api/v3/jobs/{job.id}/events"
    return data


def build_router(store: ProjectStore, jobs: JobManager) -> APIRouter:
    requirements = Requirements(store, jobs)
    documents = Documents(store, jobs)
    reviews = Reviews(store, jobs, documents)
    optimizer = Optimizer(store, jobs, documents)
    quality = Quality(store, jobs)
    base = Base(store, jobs)
    router = APIRouter(prefix="/api/v3", tags=["v3"])

    def summary(project: Project) -> dict[str, Any]:
        items = requirements.items(project.id)
        findings = base.findings(project.id)
        sections = base.sections(project.id)
        pending_questions = [
            q
            for q in requirements.questions(project.id)
            if q.state is QuestionState.PENDING and q.round == project.round
        ]
        undecided = sum(
            i.status
            in (ItemStatus.INFERRED, ItemStatus.PROPOSED, ItemStatus.ASSUMPTION)
            for i in items
        )
        open_baseline = sum(
            f.scope.value == "baseline" and f.status is FindingStatus.OPEN
            for f in findings
        )
        open_prd = sum(
            f.scope.value == "prd"
            and f.status in (FindingStatus.OPEN, FindingStatus.STALE)
            for f in findings
        )
        brief = documents.confirmed_brief(project.id) if items else None
        written = sum(bool(s.body.strip()) for s in sections)
        active = jobs.active_for(project.id)
        if not sections:
            stage = "brief" if brief is not None else "explore"
        elif written < len(sections):
            stage = "prd"
        elif open_prd or not reviews.results(project.id):
            stage = "review"
        else:
            stage = "deliver"
        return {
            **project.model_dump(mode="json"),
            "stage": stage,
            "counts": {
                "questions": len(pending_questions),
                "decide": undecided + open_baseline,
                "items": len(items),
                "sections": len(sections),
                "written": written,
                "open_findings": open_prd,
                "blocking": blocking(findings),
            },
            "brief_version": brief.version if brief else None,
            "active_job": job_view(active) if active else None,
        }

    # --- projects -----------------------------------------------------------------

    @router.get("/meta")
    async def meta() -> dict[str, Any]:
        return {
            "groups": [
                {"key": g.value, "label": label, "prefix": prefix, "core": core}
                for g, (label, prefix, core) in GROUPS.items()
            ],
            "reviewers": [r.value for r in Reviewer],
            "rubric": rubric_document(),
            "mock": jobs.gateway.is_mock,
            "provider": jobs.gateway.provider_name,
            "model": jobs.gateway.model,
        }

    @router.get("/projects")
    async def list_projects() -> dict[str, Any]:
        return {"items": [summary(p) for p in requirements.list_projects()]}

    @router.post("/projects", status_code=201)
    async def create_project(body: CreateProject) -> dict[str, Any]:
        project, job = requirements.create_project(
            text=body.text, entry_mode=body.entry_mode, name=body.name, depth=body.depth
        )
        if body.entry_mode is EntryMode.REVIEW:
            documents.import_prd(project, body.text)
        return {
            "project": summary(requirements.project(project.id)),
            "job": job_view(job) if job else None,
        }

    @router.get("/projects/{project_id}")
    async def get_project(project_id: str) -> dict[str, Any]:
        return summary(requirements.project(project_id))

    @router.patch("/projects/{project_id}")
    async def rename_project(project_id: str, body: RenameProject) -> dict[str, Any]:
        return summary(requirements.rename(project_id, body.name))

    @router.delete("/projects/{project_id}", status_code=204)
    async def delete_project(project_id: str) -> Response:
        requirements.delete(project_id)
        return Response(status_code=204)

    @router.get("/projects/{project_id}/jobs")
    async def list_jobs(project_id: str) -> dict[str, Any]:
        requirements.project(project_id)
        return {"items": [job_view(j) for j in jobs.list_for(project_id)]}

    # --- conversation and baseline ------------------------------------------------

    @router.get("/projects/{project_id}/conversation")
    async def conversation(project_id: str) -> dict[str, Any]:
        project = requirements.project(project_id)
        return {
            "round": project.round,
            "messages": [
                m.model_dump(mode="json") for m in requirements.messages(project_id)
            ],
            "questions": [
                q.model_dump(mode="json") for q in requirements.questions(project_id)
            ],
        }

    @router.post("/projects/{project_id}/turns", status_code=202)
    async def submit_turn(project_id: str, body: SubmitTurn) -> dict[str, Any]:
        job = requirements.submit_turn(
            project_id,
            answers=[a.model_dump() for a in body.answers],
            supplement=body.supplement,
            depth=body.depth,
        )
        return job_view(job)

    @router.get("/projects/{project_id}/items")
    async def list_items(project_id: str) -> dict[str, Any]:
        requirements.project(project_id)
        return {
            "items": [
                i.model_dump(mode="json")
                for i in requirements.items(project_id, include_rejected=True)
            ],
            "core_ready": requirements.core_ready(project_id),
        }

    @router.post("/projects/{project_id}/items", status_code=201)
    async def add_item(project_id: str, body: AddItem) -> dict[str, Any]:
        item = requirements.add_item(
            project_id, group=body.group, content=body.content, priority=body.priority
        )
        return item.model_dump(mode="json")

    @router.patch("/items/{item_id}")
    async def patch_item(item_id: str, body: PatchItem) -> dict[str, Any]:
        item = requirements.update_item(
            item_id,
            content=body.content,
            status=body.status,
            group=body.group,
            priority=body.priority,
            reason=body.reason,
        )
        return item.model_dump(mode="json")

    @router.get("/items/{item_id}/revisions")
    async def item_revisions(item_id: str) -> dict[str, Any]:
        return {
            "items": [
                r.model_dump(mode="json") for r in requirements.revisions(item_id)
            ]
        }

    @router.get("/projects/{project_id}/links")
    async def links(project_id: str) -> dict[str, Any]:
        return {"items": [link.model_dump() for link in requirements.links(project_id)]}

    @router.post("/projects/{project_id}/analyze", status_code=202)
    async def analyze(project_id: str, body: Analyze | None = None) -> dict[str, Any]:
        brief_id = body.brief_id if body is not None else None
        return job_view(requirements.start_analysis(project_id, brief_id))

    # --- brief and outline --------------------------------------------------------

    @router.get("/projects/{project_id}/briefs")
    async def list_briefs(project_id: str) -> dict[str, Any]:
        return {
            "items": [
                documents.public_brief(b).model_dump(mode="json")
                for b in documents.briefs(project_id)
            ]
        }

    @router.post("/projects/{project_id}/briefs", status_code=201)
    async def draft_brief(project_id: str) -> dict[str, Any]:
        brief = documents.draft_brief(project_id)
        return documents.public_brief(brief).model_dump(mode="json")

    @router.patch("/briefs/{brief_id}")
    async def edit_brief(brief_id: str, body: EditBrief) -> dict[str, Any]:
        brief = documents.edit_brief(brief_id, body.key, body.text)
        return documents.public_brief(brief).model_dump(mode="json")

    @router.post("/briefs/{brief_id}/confirm")
    async def confirm_brief(brief_id: str) -> dict[str, Any]:
        brief = documents.confirm_brief(brief_id)
        return documents.public_brief(brief).model_dump(mode="json")

    @router.post("/projects/{project_id}/outline", status_code=202)
    async def outline(project_id: str) -> dict[str, Any]:
        return job_view(documents.start_outline(project_id))

    @router.post("/projects/{project_id}/outline/confirm")
    async def confirm_outline(project_id: str) -> dict[str, Any]:
        return summary(documents.confirm_outline(project_id))

    # --- sections -----------------------------------------------------------------

    @router.get("/projects/{project_id}/sections")
    async def list_sections(project_id: str) -> dict[str, Any]:
        project = documents.project(project_id)
        return {
            "title": project.doc_title or project.name,
            "outline_confirmed": project.outline_confirmed_at is not None,
            "items": [
                s.model_dump(mode="json") for s in documents.sections(project_id)
            ],
        }

    @router.post("/projects/{project_id}/sections", status_code=201)
    async def add_section(project_id: str, body: AddSection) -> dict[str, Any]:
        section = documents.add_section(
            project_id, title=body.title, after=body.after, level=body.level
        )
        return section.model_dump(mode="json")

    @router.put("/projects/{project_id}/sections/order")
    async def reorder(project_id: str, body: Reorder) -> dict[str, Any]:
        sections = documents.reorder(project_id, [e.model_dump() for e in body.order])
        return {"items": [s.model_dump(mode="json") for s in sections]}

    @router.patch("/sections/{section_id}")
    async def save_section(section_id: str, body: SaveSection) -> dict[str, Any]:
        result = documents.save_section(
            section_id, row_version=body.row_version, body=body.body, title=body.title
        )
        return {
            "section": result["section"].model_dump(mode="json"),
            "impact": result["impact"],
        }

    @router.delete("/sections/{section_id}", status_code=204)
    async def delete_section(
        section_id: str, row_version: int = Query(ge=0)
    ) -> Response:
        documents.delete_section(section_id, row_version)
        return Response(status_code=204)

    @router.get("/sections/{section_id}/sources")
    async def section_sources(section_id: str) -> dict[str, Any]:
        return documents.sources_of(section_id)

    @router.post("/projects/{project_id}/generate", status_code=202)
    async def generate(project_id: str, body: Generate) -> dict[str, Any]:
        return job_view(documents.start_generation(project_id, body.sections))

    # --- review and findings ------------------------------------------------------

    @router.post("/projects/{project_id}/reviews", status_code=202)
    async def review(project_id: str, body: StartReview) -> dict[str, Any]:
        return job_view(reviews.start_review(project_id, body.sections))

    @router.get("/projects/{project_id}/reviews")
    async def review_results(project_id: str) -> dict[str, Any]:
        return {
            "items": [r.model_dump(mode="json") for r in reviews.results(project_id)]
        }

    @router.get("/projects/{project_id}/findings")
    async def list_findings(
        project_id: str,
        scope: str | None = None,
        reviewer: str | None = None,
        severity: str | None = None,
        section: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        base.project(project_id)
        findings = base.findings(project_id)
        if scope:
            findings = [f for f in findings if f.scope.value == scope]
        if reviewer:
            findings = [
                f for f in findings if reviewer in {r.value for r in f.reviewers}
            ]
        if severity:
            findings = [f for f in findings if f.severity.value == severity]
        if section:
            findings = [f for f in findings if section in f.related_sections]
        if status:
            findings = [f for f in findings if f.status.value == status]
        return {"items": [f.model_dump(mode="json") for f in findings]}

    @router.patch("/findings/{finding_id}")
    async def decide(finding_id: str, body: Decide) -> dict[str, Any]:
        return reviews.decide(finding_id, body.status, body.note).model_dump(
            mode="json"
        )

    @router.get("/findings/{finding_id}/history")
    async def finding_history(finding_id: str) -> dict[str, Any]:
        return {
            "items": [e.model_dump(mode="json") for e in reviews.history(finding_id)]
        }

    # --- optimisation -------------------------------------------------------------

    @router.post("/projects/{project_id}/optimize", status_code=202)
    async def optimize(project_id: str) -> dict[str, Any]:
        return job_view(optimizer.start_optimize(project_id))

    @router.get("/projects/{project_id}/proposals")
    async def list_proposals(project_id: str) -> dict[str, Any]:
        return {
            "items": [
                p.model_dump(mode="json") for p in optimizer.proposals(project_id)
            ]
        }

    @router.post("/proposals/{proposal_id}/apply")
    async def apply_proposal(proposal_id: str, body: ApplyProposal) -> dict[str, Any]:
        return optimizer.apply(proposal_id, body.changes)

    @router.post("/proposals/{proposal_id}/discard")
    async def discard_proposal(proposal_id: str) -> dict[str, Any]:
        return optimizer.discard(proposal_id).model_dump(mode="json")

    # --- versions, quality, export ------------------------------------------------

    @router.get("/projects/{project_id}/versions")
    async def list_versions(project_id: str) -> dict[str, Any]:
        return {
            "items": [v.model_dump(mode="json") for v in documents.versions(project_id)]
        }

    @router.post("/projects/{project_id}/versions", status_code=201)
    async def save_version(project_id: str, body: SaveVersion) -> dict[str, Any]:
        version = documents.create_version(
            project_id, source="human", actor="你", note=body.note or "手动保存"
        )
        return version.model_dump(mode="json", exclude={"sections"})

    @router.get("/projects/{project_id}/versions/{number}")
    async def get_version(project_id: str, number: int) -> dict[str, Any]:
        return documents.version(project_id, number).model_dump(mode="json")

    @router.get("/projects/{project_id}/versions/{a}/diff/{b}")
    async def diff(project_id: str, a: int, b: int) -> dict[str, Any]:
        return {"sections": documents.diff(project_id, a, b)}

    @router.get("/projects/{project_id}/quality")
    async def project_quality(project_id: str) -> dict[str, Any]:
        return quality.compute(project_id)

    @router.get("/projects/{project_id}/export.md", response_class=PlainTextResponse)
    async def export(project_id: str, version: int | None = None) -> PlainTextResponse:
        text = documents.export_markdown(project_id, version)
        return PlainTextResponse(text, media_type="text/markdown; charset=utf-8")

    # --- jobs ---------------------------------------------------------------------

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        base.project(job.project_id)
        return job_view(job)

    @router.post("/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict[str, Any]:
        base.project(jobs.get(job_id).project_id)
        return job_view(await jobs.cancel(job_id))

    @router.get("/jobs/{job_id}/events")
    async def job_events(
        job_id: str,
        after_sequence: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> EventSourceResponse:
        base.project(jobs.get(job_id).project_id)
        cursor = after_sequence
        if last_event_id is not None:
            try:
                cursor = max(cursor, int(last_event_id))
            except ValueError as exc:
                raise AppError(
                    "INVALID_EVENT_ID", "Last-Event-ID must be an integer.", 400
                ) from exc

        async def generate() -> AsyncIterator[dict[str, str]]:
            async for event in jobs.subscribe(job_id, cursor):
                if event is None:
                    yield {"event": "heartbeat", "data": "{}"}
                    continue
                yield {
                    "id": str(event.sequence),
                    "event": event.event,
                    "data": json.dumps(
                        event.model_dump(mode="json"), ensure_ascii=False
                    ),
                }

        return EventSourceResponse(
            generate(),
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            ping=3600,
        )

    return router
