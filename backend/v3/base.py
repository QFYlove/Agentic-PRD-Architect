"""Errors and shared helpers for the V3 services."""

from __future__ import annotations

from typing import Any

from backend.errors import AppError
from backend.v3.jobs import JobConflictError, JobManager
from backend.v3.models import (
    Finding,
    FindingEvent,
    FindingStatus,
    ItemRevision,
    ItemStatus,
    Message,
    PRDSection,
    Project,
    RequirementItem,
    now,
)
from backend.v3.rules import codes_in
from backend.v3.store import ProjectStore, new_id


class NotFound(AppError):
    def __init__(self, what: str) -> None:
        super().__init__(
            f"{what.upper()}_NOT_FOUND", f"The {what} does not exist.", 404
        )


class Invalid(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 422)


class Conflict(AppError):
    def __init__(self, code: str, message: str, current: dict[str, Any] | None = None):
        super().__init__(code, message, 409)
        self.current = current


class Base:
    """Storage access and the small helpers every service needs."""

    def __init__(self, store: ProjectStore, jobs: JobManager) -> None:
        self.store = store
        self.jobs = jobs

    # --- lookups --------------------------------------------------------------

    def project(self, project_id: str) -> Project:
        project = self.store.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise NotFound("project")
        return project

    def ensure_idle(self, project_id: str) -> None:
        """Checked before any write that precedes starting a job, so a busy
        project rejects the request without leaving half of it stored."""
        if self.jobs.active_for(project_id) is not None:
            raise JobConflictError

    def internal_codes(self, project_id: str) -> set[str]:
        """Codes the system assigned in this project that may be hidden from
        document text. A code that also appears in the user's own words is
        theirs (a product model, a ticket number) and is never hidden."""
        codes = {
            str(code)
            for table in ("v3_items", "v3_findings", "v3_sections")
            for (code,) in self.store.rows(
                f"SELECT code FROM {table} WHERE project_id = ?", (project_id,)
            )
        }
        typed: set[str] = set()
        for message in self.store.select(
            Message, "project_id = ? AND role = 'user'", (project_id,)
        ):
            typed |= codes_in(message.content)
            for answer in message.answers:
                typed |= codes_in(answer.get("answer", ""))
        return codes - typed

    def touch(self, project: Project) -> None:
        project.updated_at = now()
        self.store.update(project)

    def items(
        self, project_id: str, *, include_rejected: bool = False
    ) -> list[RequirementItem]:
        where = "project_id = ?"
        if not include_rejected:
            where += " AND status != 'rejected'"
        return self.store.select(
            RequirementItem, where, (project_id,), order="created_at, code"
        )

    def item_by_code(self, project_id: str, code: str) -> RequirementItem | None:
        rows = self.store.select(
            RequirementItem, "project_id = ? AND code = ?", (project_id, code)
        )
        return rows[0] if rows else None

    def owned_item(self, item_id: str) -> RequirementItem:
        item = self.store.get(RequirementItem, item_id)
        if item is None:
            raise NotFound("item")
        self.project(item.project_id)
        return item

    def sections(self, project_id: str) -> list[PRDSection]:
        return self.store.select(
            PRDSection, "project_id = ?", (project_id,), order="position"
        )

    def section_by_code(self, project_id: str, code: str) -> PRDSection | None:
        rows = self.store.select(
            PRDSection, "project_id = ? AND code = ?", (project_id, code)
        )
        return rows[0] if rows else None

    def resolve_section(self, project_id: str, ref: str | None) -> PRDSection | None:
        """A section from its code (``S-03``), number (``4.1``) or title."""
        if not ref:
            return None
        text = ref.strip()
        sections = self.sections(project_id)
        for section in sections:
            if section.code == text:
                return section
        import re

        number = re.match(r"^\s*§?\s*(\d+(?:\.\d+)*)", text)
        if number:
            for section in sections:
                if section.num == number.group(1):
                    return section
        for section in sections:
            if section.title and section.title in text:
                return section
        return None

    def findings(
        self, project_id: str, where: str = "1 = 1", params: tuple[Any, ...] = ()
    ) -> list[Finding]:
        return self.store.select(
            Finding,
            f"project_id = ? AND ({where})",
            (project_id, *params),
            order="created_at, code",
        )

    def finding_by_code(self, project_id: str, code: str) -> Finding | None:
        rows = self.store.select(
            Finding, "project_id = ? AND code = ?", (project_id, code)
        )
        return rows[0] if rows else None

    # --- writes with history ---------------------------------------------------

    def record_item(
        self,
        item: RequirementItem,
        *,
        before_content: str | None,
        before_status: ItemStatus | None,
        actor: str,
        reason: str | None = None,
    ) -> None:
        self.store.insert(
            ItemRevision(
                id=new_id(),
                item_id=item.id,
                before_content=before_content,
                after_content=item.content,
                before_status=before_status,
                after_status=item.status,
                actor=actor,
                reason=reason,
                created_at=now(),
            )
        )

    def set_finding_status(
        self,
        finding: Finding,
        status: FindingStatus,
        *,
        actor: str,
        note: str | None = None,
    ) -> None:
        previous = finding.status
        finding.status = status
        finding.updated_at = now()
        self.store.update(finding)
        self.store.insert(
            FindingEvent(
                id=new_id(),
                finding_id=finding.id,
                from_status=previous.value,
                to_status=status.value,
                actor=actor,
                note=note,
                created_at=now(),
            )
        )

    def add_message(self, message: Message) -> Message:
        self.store.insert(message)
        return message
