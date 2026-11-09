"""Product Brief, outline, per-section generation, editing, and versions.

The Brief is assembled by code from the baseline, not written by a model: it is
a snapshot of what the user has (and has not) confirmed, so every line traces
to an item code. A confirmed Brief is frozen; the outline and the sections only
ever read the latest confirmed one.
"""

from __future__ import annotations

from typing import Any

from backend.failures import classify
from backend.observability import log_event
from backend.schemas import RecoveryAction
from backend.v3.base import Base, Conflict, Invalid, NotFound
from backend.v3.jobs import LOGGER, JobContext
from backend.v3.llm import OutlineOutput
from backend.v3.models import (
    GROUPS,
    Brief,
    BriefSection,
    ChangeClass,
    EntryMode,
    Finding,
    FindingStatus,
    Group,
    ItemStatus,
    Job,
    JobKind,
    PRDSection,
    PRDVersion,
    Project,
    RequirementItem,
    SectionOrigin,
    SectionStatus,
    VersionSummary,
    now,
)
from backend.v3.prompts import OUTLINE_PROMPT, SECTION_PROMPT
from backend.v3.rules import (
    PROPAGATING,
    classify_change,
    line_diff,
    markdown_document,
    renumber,
    split_markdown,
    strip_internal_refs,
    summarize,
)
from backend.v3.store import new_id

STATUS_LABEL = {
    ItemStatus.INFERRED: "AI 推断",
    ItemStatus.ASSUMPTION: "假设",
    ItemStatus.PROPOSED: "AI 建议",
    ItemStatus.OPEN: "待确认",
}

#: Brief chapters (definition 3.6) and the baseline groups each is built from.
BRIEF_LAYOUT: tuple[tuple[str, str, tuple[Group, ...]], ...] = (
    ("position", "产品定位", (Group.POSITION,)),
    ("users", "目标用户", (Group.USER,)),
    ("problems", "用户问题", (Group.PROBLEM,)),
    ("scenarios", "核心使用场景", (Group.SCENARIO,)),
    ("alternatives", "现有解决方式", (Group.ALTERNATIVE,)),
    ("goals", "产品目标", (Group.GOAL,)),
    ("solution", "解决方案概述", (Group.SOLUTION,)),
    ("features", "核心功能范围", (Group.FEATURE,)),
    ("constraints", "产品约束", (Group.CONSTRAINT,)),
    ("decisions", "已确认决策", (Group.DECISION,)),
    ("assumptions", "假设", (Group.ASSUMPTION,)),
    ("open", "待确认事项", (Group.OPEN,)),
)

#: Statuses that mark a finding as needing another look after its text changed.
STALEABLE = (
    FindingStatus.OPEN,
    FindingStatus.ACCEPTED,
    FindingStatus.MODIFIED,
    FindingStatus.DEFERRED,
)


def _item_line(item: RequirementItem) -> str:
    """One Brief line. The item's code lives in ``item_codes``, not the text."""
    label = STATUS_LABEL.get(item.status)
    prefix = f"[{label}] " if label else ""
    return f"- {prefix}{item.content}"


class Documents(Base):
    # --- brief ----------------------------------------------------------------

    def briefs(self, project_id: str) -> list[Brief]:
        self.project(project_id)
        return self.store.select(
            Brief, "project_id = ?", (project_id,), order="version DESC"
        )

    def confirmed_brief(self, project_id: str) -> Brief | None:
        for brief in self.briefs(project_id):
            if brief.confirmed_at is not None:
                return brief
        return None

    def draft_brief(self, project_id: str) -> Brief:
        """Assemble a new Brief version from the current baseline."""
        self.project(project_id)
        items = self.items(project_id)
        if not items:
            raise Invalid("BASELINE_EMPTY", "Explore the idea before writing a Brief.")
        risks = self.findings(
            project_id,
            "scope = 'baseline' AND status IN ('open', 'accepted', 'modified', "
            "'deferred')",
        )
        sections: list[BriefSection] = []
        for key, title, groups in BRIEF_LAYOUT:
            members = [i for i in items if i.group in groups]
            sections.append(
                BriefSection(
                    key=key,
                    title=title,
                    text="\n".join(_item_line(i) for i in members) or "（暂无）",
                    item_codes=[i.code for i in members],
                )
            )
        sections.append(
            BriefSection(
                key="risks",
                title="风险与机会",
                text="\n".join(f"- {f.title}：{f.recommendation}" for f in risks)
                or "（暂无）",
                item_codes=sorted({c for f in risks for c in f.related_items}),
                finding_codes=[f.code for f in risks],
            )
        )
        previous = self.briefs(project_id)
        brief = Brief(
            id=new_id(),
            project_id=project_id,
            version=(previous[0].version + 1) if previous else 1,
            sections=sections,
            items=[
                {
                    "code": i.code,
                    "group": i.group.value,
                    "status": i.status.value,
                    "content": i.content,
                    "priority": i.priority.value,
                }
                for i in items
            ],
            unconfirmed_count=sum(i.status is not ItemStatus.CONFIRMED for i in items),
            created_at=now(),
        )
        self.store.insert(brief)
        self.touch(self.project(project_id))
        return brief

    def _owned_brief(self, brief_id: str) -> Brief:
        brief = self.store.get(Brief, brief_id)
        if brief is None:
            raise NotFound("brief")
        self.project(brief.project_id)
        return brief

    def edit_brief(self, brief_id: str, key: str, text: str) -> Brief:
        brief = self._owned_brief(brief_id)
        if brief.confirmed_at is not None:
            raise Conflict(
                "BRIEF_CONFIRMED",
                "A confirmed Brief cannot change. Create a new version instead.",
            )
        for section in brief.sections:
            if section.key == key:
                section.text = text.strip()
                section.edited = True
                break
        else:
            raise NotFound("brief section")
        self.store.update(brief)
        return brief

    def confirm_brief(self, brief_id: str) -> Brief:
        brief = self._owned_brief(brief_id)
        if brief.confirmed_at is None:
            brief.confirmed_at = now()
            self.store.update(brief)
            self.touch(self.project(brief.project_id))
        return brief

    def public_brief(self, brief: Brief) -> Brief:
        """The Brief as a reader sees it.

        Briefs saved before codes were moved out of the text still carry
        "（POS-01）" after each line; those references are removed here, on
        read, so the frozen snapshot itself is never rewritten.
        """
        codes = self.internal_codes(brief.project_id)
        view = brief.model_copy(deep=True)
        for section in view.sections:
            section.text = strip_internal_refs(section.text, codes)
        return view

    def _brief_payload(
        self, brief: Brief, *, with_codes: bool = False
    ) -> dict[str, Any]:
        """What a generator reads. Only the outline step, which must link
        sections to items, receives codes -- and only in structured fields."""
        clean = self.public_brief(brief)
        payload: dict[str, Any] = {
            "version": brief.version,
            "sections": [
                {"title": s.title, "text": s.text}
                | ({"item_codes": s.item_codes} if with_codes else {})
                for s in clean.sections
            ],
            "unconfirmed_items": brief.unconfirmed_count,
        }
        if with_codes:
            payload["items"] = [
                {k: item[k] for k in ("code", "group", "status", "content")}
                for item in brief.items
            ]
        return payload

    # --- outline --------------------------------------------------------------

    def start_outline(self, project_id: str) -> Job:
        project = self.project(project_id)
        self.ensure_idle(project_id)
        brief = self.confirmed_brief(project_id)
        if brief is None:
            raise Invalid("BRIEF_NOT_CONFIRMED", "Confirm the Product Brief first.")
        if any(s.body.strip() for s in self.sections(project_id)):
            raise Conflict(
                "DOCUMENT_EXISTS",
                "The document already has content; edit the outline instead.",
            )
        payload = {"brief": self._brief_payload(brief, with_codes=True)}
        codes = {str(item["code"]) for item in brief.items}

        async def run(ctx: JobContext) -> dict[str, Any]:
            output = await ctx.structured(
                task="outline",
                instructions=OUTLINE_PROMPT,
                payload=payload,
                schema=OutlineOutput,
            )
            return self.apply_outline(project.id, output, codes)

        return self.jobs.start(
            project_id=project_id,
            kind=JobKind.OUTLINE,
            input={"brief_version": brief.version},
            runner=run,
        )

    def apply_outline(
        self, project_id: str, output: OutlineOutput, brief_codes: set[str]
    ) -> dict[str, Any]:
        project = self.project(project_id)
        levels = [entry.level for entry in output.sections]
        numbers = renumber(levels)
        codes = self.internal_codes(project_id)
        old_to_new = {
            entry.num: number
            for entry, number in zip(output.sections, numbers, strict=True)
        }
        with self.store.transaction():
            self.store.delete(PRDSection, "project_id = ?", (project_id,))
            for position, (entry, number) in enumerate(
                zip(output.sections, numbers, strict=True)
            ):
                section = PRDSection(
                    id=new_id(),
                    project_id=project_id,
                    code=self.store.next_code(project_id, "S"),
                    position=position,
                    level=1 if number.count(".") == 0 else 2,
                    num=number,
                    title=strip_internal_refs(entry.title.strip(), codes),
                    goal=strip_internal_refs(entry.goal.strip(), codes),
                    contents=[c.strip() for c in entry.contents if c.strip()],
                    item_codes=[c for c in entry.item_codes if c in brief_codes],
                    depends=[old_to_new[d] for d in entry.depends if d in old_to_new],
                    open_points=[p.strip() for p in entry.open_points if p.strip()],
                    origin=SectionOrigin.AI,
                    status=SectionStatus.PLANNED,
                    row_version=1,
                    updated_at=now(),
                )
                self.store.insert(section)
                self.store.replace_links(
                    project_id, section.code, "derives", section.item_codes
                )
            project.doc_title = output.title.strip()
            project.outline_confirmed_at = None
            self.touch(project)
        return {"sections": len(output.sections)}

    def add_section(
        self, project_id: str, *, title: str, after: str | None, level: int
    ) -> PRDSection:
        self.project(project_id)
        if not title.strip():
            raise Invalid("TITLE_REQUIRED", "A section needs a title.")
        sections = self.sections(project_id)
        index = len(sections)
        if after:
            for position, section in enumerate(sections):
                if section.code == after:
                    index = position + 1
        section = PRDSection(
            id=new_id(),
            project_id=project_id,
            code=self.store.next_code(project_id, "S"),
            position=index,
            level=1 if level <= 1 else 2,
            num="",
            title=title.strip(),
            origin=SectionOrigin.HUMAN,
            status=SectionStatus.PLANNED,
            row_version=1,
            updated_at=now(),
        )
        sections.insert(index, section)
        with self.store.transaction():
            self.store.insert(section)
            self._renumber(sections)
        return section

    def reorder(self, project_id: str, order: list[dict[str, Any]]) -> list[PRDSection]:
        """``order`` is the full list of ``{"code", "level"}`` in the new order."""
        sections = {s.code: s for s in self.sections(project_id)}
        if sorted(entry["code"] for entry in order) != sorted(sections):
            raise Invalid("ORDER_INCOMPLETE", "List every section exactly once.")
        arranged: list[PRDSection] = []
        for entry in order:
            section = sections[entry["code"]]
            section.level = 1 if int(entry.get("level", section.level)) <= 1 else 2
            arranged.append(section)
        with self.store.transaction():
            self._renumber(arranged)
        return self.sections(project_id)

    def _renumber(self, sections: list[PRDSection]) -> None:
        numbers = renumber([s.level for s in sections])
        for position, (section, number) in enumerate(
            zip(sections, numbers, strict=True)
        ):
            section.position = position
            section.num = number
            section.level = 1 if "." not in number else 2
            self.store.update(section)

    def owned_section(self, section_id: str) -> PRDSection:
        section = self.store.get(PRDSection, section_id)
        if section is None:
            raise NotFound("section")
        self.project(section.project_id)
        return section

    def delete_section(self, section_id: str, row_version: int) -> None:
        section = self.owned_section(section_id)
        if section.row_version != row_version:
            raise Conflict("SECTION_CHANGED", "The section changed. Reload it first.")
        with self.store.transaction():
            self.store.delete(PRDSection, "id = ?", (section.id,))
            remaining = self.sections(section.project_id)
            self._renumber(remaining)
            self._mark_stale(section.project_id, [section.code], note="章节已删除")

    def confirm_outline(self, project_id: str) -> Project:
        project = self.project(project_id)
        if not self.sections(project_id):
            raise Invalid("OUTLINE_EMPTY", "The outline has no sections.")
        project.outline_confirmed_at = now()
        self.touch(project)
        return project

    # --- generation -------------------------------------------------------------

    def start_generation(self, project_id: str, codes: list[str] | None) -> Job:
        """Write every planned or failed section (or just ``codes``), in order."""
        project = self.project(project_id)
        self.ensure_idle(project_id)
        if project.outline_confirmed_at is None:
            raise Invalid("OUTLINE_NOT_CONFIRMED", "Confirm the outline first.")
        brief = self.confirmed_brief(project_id)
        if brief is None:
            raise Invalid("BRIEF_NOT_CONFIRMED", "Confirm the Product Brief first.")
        sections = self.sections(project_id)
        if codes:
            targets = [s for s in sections if s.code in set(codes)]
            human = [
                s.code for s in targets if s.origin is SectionOrigin.HUMAN and s.body
            ]
            if human:
                raise Conflict(
                    "HUMAN_SECTION",
                    "Sections you wrote are never regenerated; edit them instead.",
                )
        else:
            targets = [
                s
                for s in sections
                if s.status in (SectionStatus.PLANNED, SectionStatus.FAILED)
            ]
        if not targets:
            raise Invalid("NOTHING_TO_GENERATE", "Every section already has content.")
        target_codes = [s.code for s in targets]
        brief_payload = self._brief_payload(brief)
        brief_items = {str(i["code"]): i for i in brief.items}

        async def run(ctx: JobContext) -> dict[str, Any]:
            done: list[str] = []
            failed: list[str] = []
            last_error: Exception | None = None
            for code in target_codes:
                section = self.section_by_code(project_id, code)
                if section is None:
                    continue
                error = await self._generate_one(
                    ctx, section, brief_payload, brief_items
                )
                if error is None:
                    done.append(code)
                    continue
                failed.append(code)
                last_error = error
                # A configuration problem fails every section the same way;
                # stop instead of paying for N identical failures.
                info = classify(error, has_best_version=False)
                if info.recovery_action is RecoveryAction.CHECK_CONFIGURATION:
                    break
            if not done and last_error is not None:
                raise last_error
            version = None
            if done and all(
                s.status is SectionStatus.DONE for s in self.sections(project_id)
            ):
                version = self.create_version(
                    project_id,
                    source="ai_generate",
                    actor="AI 生成",
                    note=f"基于 Brief v{brief.version} 逐章生成",
                    section_codes=done,
                ).number
            return {"done": done, "failed": failed, "version": version}

        return self.jobs.start(
            project_id=project_id,
            kind=JobKind.GENERATE,
            input={"sections": target_codes},
            runner=run,
        )

    async def _generate_one(
        self,
        ctx: JobContext,
        section: PRDSection,
        brief_payload: dict[str, Any],
        brief_items: dict[str, dict[str, Any]],
    ) -> Exception | None:
        """Write one section. Returns the error instead of raising, so one
        failed section never discards the others."""
        all_sections = self.sections(section.project_id)
        payload = {
            "brief": brief_payload,
            "section": {
                "num": section.num,
                "title": section.title,
                "goal": section.goal,
                "contents": section.contents,
                "depends": section.depends,
                "open_points": section.open_points,
            },
            "items": [
                {k: v for k, v in brief_items[c].items() if k != "code"}
                for c in section.item_codes
                if c in brief_items
            ],
            "outline": [{"num": s.num, "title": s.title} for s in all_sections],
            "previous": [
                {"num": s.num, "title": s.title, "summary": s.summary}
                for s in all_sections
                if s.position < section.position and s.summary
            ],
        }
        section.status = SectionStatus.GENERATING
        section.error = None
        self.store.update(section)
        await ctx.emit("section_started", {"code": section.code, "num": section.num})

        async def on_delta(delta: str) -> None:
            await ctx.emit("section_delta", {"code": section.code, "delta": delta})

        async def on_reset() -> None:
            await ctx.emit("section_reset", {"code": section.code})

        try:
            body = await ctx.stream_text(
                task="section",
                instructions=SECTION_PROMPT,
                payload=payload,
                on_delta=on_delta,
                on_reset=on_reset,
            )
        except Exception as exc:
            info = classify(exc, has_best_version=False)
            current = self.section_by_code(section.project_id, section.code)
            if current is not None:
                current.status = SectionStatus.FAILED
                current.error = info.message
                self.store.update(current)
            log_event(
                LOGGER,
                "section_failed",
                job_id=ctx.job.id,
                section=section.code,
                code=info.code,
            )
            await ctx.emit(
                "section_failed",
                {"code": section.code, "error": info.code, "message": info.message},
            )
            return exc
        # The prompt forbids internal codes; a model that writes one anyway
        # does not get it into the document.
        body = strip_internal_refs(body, self.internal_codes(section.project_id))
        current = self.section_by_code(section.project_id, section.code)
        if current is None:
            return None
        current.body = body
        current.summary = summarize(body)
        current.status = SectionStatus.DONE
        current.origin = SectionOrigin.AI
        current.row_version += 1
        current.updated_at = now()
        self.store.update(current)
        await ctx.emit(
            "section_done",
            {"code": current.code, "body": body, "row_version": current.row_version},
        )
        return None

    # --- editing --------------------------------------------------------------

    def save_section(
        self,
        section_id: str,
        *,
        row_version: int,
        body: str | None,
        title: str | None,
    ) -> dict[str, Any]:
        """Save a human edit with optimistic locking, then work out its impact."""
        section = self.owned_section(section_id)
        if section.row_version != row_version:
            raise Conflict(
                "SECTION_CHANGED",
                "Someone else changed this section. Reload it before saving.",
                current=section.model_dump(mode="json"),
            )
        before_body, before_title = section.body, section.title
        new_body = before_body if body is None else body.strip()
        new_title = (
            before_title if title is None or not title.strip() else title.strip()
        )
        change = classify_change(new_title, before_body, new_body)
        if new_title != before_title and change is ChangeClass.FORMAT:
            change = ChangeClass.DESCRIPTION
        with self.store.transaction():
            section.body = new_body
            section.title = new_title
            section.summary = summarize(new_body)
            if new_body:
                section.status = SectionStatus.DONE
            if change is not ChangeClass.FORMAT:
                section.origin = SectionOrigin.HUMAN
            section.needs_recheck = False
            section.row_version += 1
            section.updated_at = now()
            self.store.update(section)
            impact = self.impact_of(section, change)
            self.touch(self.project(section.project_id))
        return {"section": section, "impact": impact}

    def impact_of(self, section: PRDSection, change: ChangeClass) -> dict[str, Any]:
        """Deterministic impact of one changed section (no model call).

        A formatting change touches nothing. Any other change makes this
        section's open findings stale. Feature, rule, positioning and
        constraint changes also flag the sections that depend on this one, or
        share a baseline item with it, for a recheck.
        """
        if change is ChangeClass.FORMAT:
            return {"change": change.value, "sections": [], "stale": []}
        stale = self._mark_stale(section.project_id, [section.code], note="章节已修改")
        affected: list[str] = []
        if change in PROPAGATING:
            for other in self.sections(section.project_id):
                if other.code == section.code or not other.body:
                    continue
                depends = section.num in other.depends
                shares = bool(set(other.item_codes) & set(section.item_codes))
                cites = section.num in other.body and f"{section.num} " in other.body
                acceptance = "验收" in other.title or "规则" in other.title
                if depends or (shares and acceptance) or cites:
                    other.needs_recheck = True
                    self.store.update(other)
                    affected.append(other.code)
            stale += self._mark_stale(
                section.project_id, affected, note=f"{section.num} 已修改，需要复查"
            )
        return {"change": change.value, "sections": affected, "stale": stale}

    def _mark_stale(self, project_id: str, codes: list[str], *, note: str) -> list[str]:
        if not codes:
            return []
        marked: list[str] = []
        for finding in self.findings(project_id, "scope = 'prd'"):
            if finding.status not in STALEABLE:
                continue
            if not set(finding.related_sections) & set(codes):
                continue
            self.set_finding_status(
                finding, FindingStatus.STALE, actor="system", note=note
            )
            marked.append(finding.code)
        return marked

    # --- versions ---------------------------------------------------------------

    def create_version(
        self,
        project_id: str,
        *,
        source: str,
        actor: str,
        note: str,
        section_codes: list[str] | None = None,
        finding_codes: list[str] | None = None,
    ) -> PRDVersion:
        """Append a snapshot. Earlier versions are never rewritten."""
        sections = self.sections(project_id)
        if not any(s.body for s in sections):
            raise Invalid("DOCUMENT_EMPTY", "There is no document content to save.")
        last = self.store.scalar(
            "SELECT MAX(number) FROM v3_versions WHERE project_id = ?", (project_id,)
        )
        number = int(last or 0) + 1
        if section_codes is None:
            previous = self.versions(project_id)
            section_codes = (
                self._changed_codes(
                    self.version(project_id, previous[0].number), sections
                )
                if previous
                else [s.code for s in sections]
            )
        version = PRDVersion(
            id=new_id(),
            project_id=project_id,
            number=number,
            label=f"v{number}",
            source=source,
            actor=actor,
            note=note.strip() or "保存版本",
            finding_codes=finding_codes or [],
            section_codes=section_codes,
            sections=[
                {
                    "code": s.code,
                    "num": s.num,
                    "level": s.level,
                    "title": s.title,
                    "body": s.body,
                    "origin": s.origin.value,
                }
                for s in sections
            ],
            created_at=now(),
        )
        self.store.insert(version)
        return version

    @staticmethod
    def _changed_codes(previous: PRDVersion, sections: list[PRDSection]) -> list[str]:
        old = {str(s["code"]): s for s in previous.sections}
        changed = [
            s.code
            for s in sections
            if s.code not in old
            or old[s.code]["body"] != s.body
            or old[s.code]["title"] != s.title
        ]
        removed = [code for code in old if code not in {s.code for s in sections}]
        return changed + removed

    def versions(self, project_id: str) -> list[VersionSummary]:
        self.project(project_id)
        rows = self.store.select(
            PRDVersion, "project_id = ?", (project_id,), order="number DESC"
        )
        return [
            VersionSummary.model_validate(r.model_dump(exclude={"sections"}))
            for r in rows
        ]

    def version(self, project_id: str, number: int) -> PRDVersion:
        self.project(project_id)
        rows = self.store.select(
            PRDVersion, "project_id = ? AND number = ?", (project_id, number)
        )
        if not rows:
            raise NotFound("version")
        return rows[0]

    def diff(self, project_id: str, a: int, b: int) -> list[dict[str, Any]]:
        """Section-level comparison of two versions, as line diffs."""
        left = {str(s["code"]): s for s in self.version(project_id, a).sections}
        right_version = self.version(project_id, b)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for section in right_version.sections:
            code = str(section["code"])
            seen.add(code)
            before = left.get(code)
            if before is None:
                out.append(
                    {
                        "code": code,
                        "num": section["num"],
                        "title": section["title"],
                        "kind": "added",
                        "lines": line_diff("", str(section["body"])),
                    }
                )
            elif (
                before["body"] != section["body"] or before["title"] != section["title"]
            ):
                out.append(
                    {
                        "code": code,
                        "num": section["num"],
                        "title": section["title"],
                        "kind": "changed",
                        "lines": line_diff(str(before["body"]), str(section["body"])),
                    }
                )
        for code, section in left.items():
            if code not in seen:
                out.append(
                    {
                        "code": code,
                        "num": section["num"],
                        "title": section["title"],
                        "kind": "removed",
                        "lines": line_diff(str(section["body"]), ""),
                    }
                )
        return out

    # --- export / import ----------------------------------------------------------

    def export_markdown(self, project_id: str, number: int | None = None) -> str:
        project = self.project(project_id)
        if number is not None:
            rows = [
                (int(s["level"]), str(s["num"]), str(s["title"]), str(s["body"]))
                for s in self.version(project_id, number).sections
            ]
        else:
            rows = [
                (s.level, s.num, s.title, s.body) for s in self.sections(project_id)
            ]
        return markdown_document(
            project.doc_title or project.name, rows, self.internal_codes(project_id)
        )

    def import_prd(self, project: Project, text: str) -> list[PRDSection]:
        """Entry C: cut a pasted PRD into editable sections, ready for review."""
        if project.entry_mode is not EntryMode.REVIEW:
            raise Invalid("WRONG_ENTRY", "Only review projects import a PRD.")
        title, parts = split_markdown(text)
        sections = []
        with self.store.transaction():
            for position, (level, heading, body) in enumerate(parts):
                section = PRDSection(
                    id=new_id(),
                    project_id=project.id,
                    code=self.store.next_code(project.id, "S"),
                    position=position,
                    level=level,
                    num="",
                    title=heading,
                    body=body,
                    summary=summarize(body),
                    origin=SectionOrigin.HUMAN,
                    status=SectionStatus.DONE,
                    row_version=1,
                    updated_at=now(),
                )
                self.store.insert(section)
                sections.append(section)
            self._renumber(sections)
            project.doc_title = title or project.name
            project.outline_confirmed_at = now()
            self.touch(project)
            self.create_version(
                project.id, source="import", actor="你", note="导入已有 PRD"
            )
        return sections

    # --- traceability -------------------------------------------------------------

    def sources_of(self, section_id: str) -> dict[str, Any]:
        section = self.owned_section(section_id)
        items = {
            i.code: i for i in self.items(section.project_id, include_rejected=True)
        }
        findings: list[Finding] = [
            f
            for f in self.findings(section.project_id, "scope = 'prd'")
            if section.code in f.related_sections
        ]
        return {
            "items": [
                {
                    "code": code,
                    "group": GROUPS[items[code].group][0],
                    "status": items[code].status.value,
                    "content": items[code].content,
                }
                for code in section.item_codes
                if code in items
            ],
            "depends": section.depends,
            "findings": [f.code for f in findings],
        }
