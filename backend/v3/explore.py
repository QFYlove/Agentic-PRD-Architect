"""Projects, the conversation, the requirement baseline, and the Analyst.

The rule this module exists to enforce: a model never decides what the user
has agreed to. Explorer output is lowered to an AI-assignable status before it
is stored, a ``user`` source must quote the user's own words exactly or it is
downgraded to ``ai``, and only the item endpoints -- which only a user calls --
can set ``confirmed`` or ``rejected``.
"""

from __future__ import annotations

from typing import Any

from backend.language import detect_output_language
from backend.v3.base import Base, Invalid, NotFound
from backend.v3.jobs import JobContext
from backend.v3.llm import AnalystOutput, ExplorerOutput
from backend.v3.models import (
    AI_ASSIGNABLE_STATUSES,
    CORE_GROUPS,
    GROUPS,
    AnalystKind,
    Brief,
    Depth,
    EntryMode,
    Finding,
    FindingScope,
    FindingStatus,
    Group,
    ItemRevision,
    ItemStatus,
    Job,
    JobKind,
    Link,
    Message,
    Priority,
    Project,
    Question,
    QuestionState,
    RequirementItem,
    Reviewer,
    SourceKind,
    Verification,
    now,
)
from backend.v3.prompts import ANALYST_PROMPT, EXPLORER_PROMPT
from backend.v3.rules import guard_severity, quote_in, same_problem, similar_text
from backend.v3.store import new_id

#: Rounds of conversation sent to the Explorer. Older rounds live in the baseline.
RECENT_ROUNDS = 3
MAX_QUESTIONS = {Depth.BRIEF: 2, Depth.DETAILED: 3}
UNDECIDED = (
    ItemStatus.INFERRED,
    ItemStatus.PROPOSED,
    ItemStatus.ASSUMPTION,
    ItemStatus.OPEN,
)

#: Asked only when the model returns no question and a core group is empty.
FALLBACK_QUESTIONS: dict[Group, tuple[str, str]] = {
    Group.POSITION: (
        "用一句话说，这个产品是什么、给谁用？",
        "产品定位决定后面每个功能的取舍。",
    ),
    Group.USER: (
        "最核心的用户是谁？他们现在处在什么情况？",
        "先确定为谁设计，才能判断哪些问题最值得解决。",
    ),
    Group.PROBLEM: (
        "这些用户现在遇到的最大问题是什么？",
        "核心问题决定 MVP 必须包含什么。",
    ),
    Group.SCENARIO: (
        "用户会在什么时候、为了完成什么事使用它？",
        "具体场景决定核心流程怎么设计。",
    ),
}


class Requirements(Base):
    # --- projects ---------------------------------------------------------------

    def create_project(
        self,
        *,
        text: str,
        entry_mode: EntryMode,
        name: str | None,
        depth: Depth,
    ) -> tuple[Project, Job | None]:
        text = text.strip()
        if len(text) < 4:
            raise Invalid("INPUT_TOO_SHORT", "Describe the product in a few words.")
        number = self.store.next_number("_global", "P")
        title = (name or "").strip() or _default_name(text)
        project = Project(
            id=new_id(),
            code=f"P-{number:04d}",
            name=title[:60],
            entry_mode=entry_mode,
            depth=depth,
            language=detect_output_language(text),
            round=1,
            created_at=now(),
            updated_at=now(),
        )
        self.store.insert(project)
        if entry_mode is EntryMode.REVIEW:
            return project, None
        self.add_message(
            Message(
                id=new_id(),
                project_id=project.id,
                round=1,
                role="user",
                kind="initial",
                content=text,
                created_at=now(),
            )
        )
        job = self.start_explore(project, this_round={"initial_input": text})
        return project, job

    def rename(self, project_id: str, name: str) -> Project:
        project = self.project(project_id)
        if not name.strip():
            raise Invalid("NAME_REQUIRED", "A project needs a name.")
        project.name = name.strip()[:60]
        self.touch(project)
        return project

    def delete(self, project_id: str) -> None:
        """Soft delete: the rows stay, but no endpoint returns the project again."""
        project = self.project(project_id)
        project.deleted_at = now()
        self.store.update(project)

    def list_projects(self) -> list[Project]:
        return self.store.select(Project, "deleted_at IS NULL", order="updated_at DESC")

    # --- conversation ---------------------------------------------------------

    def messages(self, project_id: str) -> list[Message]:
        return self.store.select(
            Message, "project_id = ?", (project_id,), order="created_at"
        )

    def questions(self, project_id: str) -> list[Question]:
        return self.store.select(
            Question, "project_id = ?", (project_id,), order="created_at, code"
        )

    def pending_questions(self, project: Project) -> list[Question]:
        return [
            q
            for q in self.questions(project.id)
            if q.state is QuestionState.PENDING and q.round == project.round
        ]

    def submit_turn(
        self,
        project_id: str,
        *,
        answers: list[dict[str, str]],
        supplement: str,
        depth: Depth | None,
    ) -> Job:
        project = self.project(project_id)
        self.ensure_idle(project_id)
        if depth is not None and depth is not project.depth:
            project.depth = depth
            self.store.update(project)
        pending = {q.code: q for q in self.pending_questions(project)}
        recorded: list[dict[str, str]] = []
        with self.store.transaction():
            for answer in answers:
                question = pending.get(answer.get("question", ""))
                if question is None:
                    continue
                kind = answer.get("kind", "answer")
                text = answer.get("text", "").strip()
                if kind == "answer" and text:
                    question.state = QuestionState.ANSWERED
                    question.answer = text
                elif kind == "unknown":
                    question.state = QuestionState.UNKNOWN
                else:
                    question.state = QuestionState.SKIPPED
                    kind = "skip"
                self.store.update(question)
                recorded.append(
                    {
                        "question": question.code,
                        "text": question.text,
                        "group": question.target_group.value,
                        "kind": kind,
                        "answer": text if kind == "answer" else "",
                    }
                )
                if kind in {"skip", "unknown"}:
                    self._open_item_for(project, question, kind)
            supplement = supplement.strip()
            if not recorded and not supplement:
                raise Invalid("EMPTY_TURN", "Answer, skip, or add something first.")
            content = "\n".join(
                f"{r['text']}\n{r['answer']}" for r in recorded if r["answer"]
            )
            if supplement:
                content = f"{content}\n{supplement}".strip()
            self.add_message(
                Message(
                    id=new_id(),
                    project_id=project.id,
                    round=project.round,
                    role="user",
                    kind="answer" if recorded else "supplement",
                    content=content,
                    answers=recorded,
                    created_at=now(),
                )
            )
        return self.start_explore(
            project, this_round={"answers": recorded, "supplement": supplement}
        )

    def _open_item_for(self, project: Project, question: Question, kind: str) -> None:
        code = self.store.next_code(project.id, GROUPS[Group.OPEN][1])
        item = RequirementItem(
            id=new_id(),
            project_id=project.id,
            code=code,
            group=Group.OPEN,
            content=question.text,
            status=ItemStatus.OPEN,
            source_kind=SourceKind.AI,
            source_round=project.round,
            priority=question.priority,
            reason="你跳过了这个问题" if kind == "skip" else "你暂时不确定",
            links=[question.target_group.value],
            created_at=now(),
            updated_at=now(),
        )
        self.store.insert(item)
        self.record_item(item, before_content=None, before_status=None, actor="user")

    # --- explorer -------------------------------------------------------------

    def _user_texts(self, project_id: str) -> list[str]:
        texts: list[str] = []
        for message in self.messages(project_id):
            if message.role != "user":
                continue
            texts.append(message.content)
            texts.extend(a.get("answer", "") for a in message.answers)
        return texts

    def explorer_payload(
        self, project: Project, this_round: dict[str, Any]
    ) -> dict[str, Any]:
        items = self.items(project.id, include_rejected=True)
        messages = self.messages(project.id)
        recent = [
            {"round": m.round, "role": m.role, "content": m.content}
            for m in messages
            if m.round > project.round - RECENT_ROUNDS
        ]
        focus = [
            {"code": f.code, "title": f.title, "recommendation": f.recommendation}
            for f in self.findings(
                project.id,
                "scope = ? AND status IN (?, ?)",
                (FindingScope.BASELINE.value, "accepted", "modified"),
            )
            if not any(q.finding_code == f.code for q in self.questions(project.id))
        ]
        return {
            "depth": project.depth.value,
            "round": project.round,
            "baseline": [
                {
                    "code": i.code,
                    "group": i.group.value,
                    "status": i.status.value,
                    "content": i.content,
                }
                for i in items
                if i.status is not ItemStatus.REJECTED
            ],
            "rejected": [i.content for i in items if i.status is ItemStatus.REJECTED],
            "recent_rounds": recent,
            "this_round": this_round,
            "asked_questions": [q.text for q in self.questions(project.id)],
            "focus_findings": focus,
        }

    def start_explore(self, project: Project, *, this_round: dict[str, Any]) -> Job:
        payload = self.explorer_payload(project, this_round)
        round_number = project.round

        async def run(ctx: JobContext) -> dict[str, Any]:
            output = await ctx.structured(
                task="explore",
                instructions=EXPLORER_PROMPT,
                payload=payload,
                schema=ExplorerOutput,
            )
            return self.apply_explorer(project.id, round_number, output, ctx.job.id)

        return self.jobs.start(
            project_id=project.id,
            kind=JobKind.EXPLORE,
            input={"round": round_number},
            runner=run,
        )

    def apply_explorer(
        self, project_id: str, round_number: int, output: ExplorerOutput, job_id: str
    ) -> dict[str, Any]:
        """Store one Explorer result under the baseline rules. Returns counts."""
        project = self.project(project_id)
        user_texts = self._user_texts(project_id)
        all_items = self.items(project_id, include_rejected=True)
        changes: list[dict[str, str]] = []
        dropped = 0
        with self.store.transaction():
            for extracted in output.items:
                status = extracted.status
                if status not in AI_ASSIGNABLE_STATUSES:
                    # Confirmed and rejected are user decisions; a model that
                    # claims either is lowered to an inference.
                    status = ItemStatus.INFERRED
                if extracted.group is Group.OPEN:
                    status = ItemStatus.OPEN
                source = extracted.source_kind
                quote: str | None = extracted.source_quote.strip() or None
                if source is SourceKind.USER and not (
                    quote and quote_in(quote, user_texts)
                ):
                    source, quote = SourceKind.AI, None
                if source is SourceKind.AI:
                    quote = None
                target = (
                    next((i for i in all_items if i.code == extracted.code), None)
                    if extracted.code
                    else None
                )
                rejected = [
                    i
                    for i in all_items
                    if i.status is ItemStatus.REJECTED and i.group is extracted.group
                ]
                if any(
                    similar_text(extracted.content, i.content, 0.7) for i in rejected
                ):
                    dropped += 1
                    continue
                if target is not None and target.status is ItemStatus.REJECTED:
                    dropped += 1
                    continue
                if target is not None and target.status is not ItemStatus.CONFIRMED:
                    if target.content == extracted.content and target.status is status:
                        continue
                    before = (target.content, target.status)
                    target.content = extracted.content
                    target.status = status
                    target.reason = extracted.reason or target.reason
                    if source is SourceKind.USER:
                        target.source_kind, target.source_quote = source, quote
                    target.updated_at = now()
                    self.store.update(target)
                    self.record_item(
                        target,
                        before_content=before[0],
                        before_status=before[1],
                        actor="ai",
                        reason=extracted.reason or None,
                    )
                    changes.append({"item": target.code, "kind": "updated"})
                    continue
                duplicate = any(
                    i.group is extracted.group
                    and i.status is not ItemStatus.REJECTED
                    and similar_text(extracted.content, i.content, 0.85)
                    for i in all_items
                )
                if duplicate:
                    continue
                links: list[str] = []
                reason = extracted.reason or None
                if target is not None:
                    # A confirmed item is never rewritten by a model. The change
                    # becomes a new item linked to it, for the user to decide.
                    links = [target.code]
                    reason = f"可能需要更新 {target.code}：{reason or ''}".rstrip("：")
                item = RequirementItem(
                    id=new_id(),
                    project_id=project_id,
                    code=self.store.next_code(project_id, GROUPS[extracted.group][1]),
                    group=extracted.group,
                    content=extracted.content,
                    status=status,
                    source_kind=source,
                    source_round=round_number,
                    source_quote=quote,
                    priority=extracted.priority,
                    reason=reason,
                    links=links,
                    created_at=now(),
                    updated_at=now(),
                )
                self.store.insert(item)
                all_items.append(item)
                self.record_item(
                    item, before_content=None, before_status=None, actor="ai"
                )
                changes.append({"item": item.code, "kind": "added"})
            questions = self._store_questions(project, output, round_number)
            used = [q.finding_code for q in questions if q.finding_code]
            self.add_message(
                Message(
                    id=new_id(),
                    project_id=project_id,
                    round=round_number,
                    role="ai",
                    kind="reply",
                    content=output.understanding.strip(),
                    changes=changes,
                    finding_codes=[code for code in used if code],
                    job_id=job_id,
                    created_at=now(),
                )
            )
            project.round = round_number + 1
            self.touch(project)
        return {
            "round": round_number,
            "changes": len(changes),
            "dropped": dropped,
            "questions": [q.code for q in questions],
            "ready_for_brief": output.ready_for_brief and self.core_ready(project_id),
        }

    def _store_questions(
        self, project: Project, output: ExplorerOutput, round_number: int
    ) -> list[Question]:
        asked = [q.text for q in self.questions(project.id)]
        confirmed = [
            i.content
            for i in self.items(project.id)
            if i.status is ItemStatus.CONFIRMED
        ]
        finding_codes = {f.code for f in self.findings(project.id)}
        kept: list[Question] = []
        candidates = sorted(output.questions, key=lambda q: q.priority.value)
        for candidate in candidates:
            text = candidate.text.strip()
            if any(similar_text(text, previous, 0.6) for previous in asked):
                continue
            if any(similar_text(text, fact, 0.7) for fact in confirmed):
                continue
            kept.append(
                Question(
                    id=new_id(),
                    project_id=project.id,
                    code=self.store.next_code(project.id, "Q"),
                    round=round_number + 1,
                    priority=candidate.priority,
                    text=text,
                    purpose=candidate.purpose.strip(),
                    target_group=candidate.target_group,
                    finding_code=(
                        candidate.finding_code
                        if candidate.finding_code in finding_codes
                        else None
                    ),
                    state=QuestionState.PENDING,
                    created_at=now(),
                )
            )
            asked.append(text)
            if len(kept) >= MAX_QUESTIONS[project.depth]:
                break
        if not kept:
            present = {i.group for i in self.items(project.id)}
            for group in CORE_GROUPS:
                text, purpose = FALLBACK_QUESTIONS[group]
                if group in present or any(similar_text(text, a, 0.6) for a in asked):
                    continue
                kept.append(
                    Question(
                        id=new_id(),
                        project_id=project.id,
                        code=self.store.next_code(project.id, "Q"),
                        round=round_number + 1,
                        priority=Priority.P0,
                        text=text,
                        purpose=purpose,
                        target_group=group,
                        state=QuestionState.PENDING,
                        created_at=now(),
                    )
                )
                break
        for question in kept:
            self.store.insert(question)
        return kept

    def core_ready(self, project_id: str) -> bool:
        confirmed = {
            i.group for i in self.items(project_id) if i.status is ItemStatus.CONFIRMED
        }
        return all(group in confirmed for group in CORE_GROUPS)

    # --- user edits -----------------------------------------------------------

    def add_item(
        self,
        project_id: str,
        *,
        group: Group,
        content: str,
        priority: Priority,
    ) -> RequirementItem:
        """An item the user writes directly is theirs, so it is confirmed."""
        project = self.project(project_id)
        content = content.strip()
        if not content:
            raise Invalid("CONTENT_REQUIRED", "An item needs content.")
        item = RequirementItem(
            id=new_id(),
            project_id=project_id,
            code=self.store.next_code(project_id, GROUPS[group][1]),
            group=group,
            content=content,
            status=ItemStatus.CONFIRMED,
            source_kind=SourceKind.USER,
            source_round=project.round,
            source_quote=content,
            priority=priority,
            created_at=now(),
            updated_at=now(),
        )
        with self.store.transaction():
            self.store.insert(item)
            self.add_message(
                Message(
                    id=new_id(),
                    project_id=project_id,
                    round=project.round,
                    role="user",
                    kind="edit",
                    content=content,
                    changes=[{"item": item.code, "kind": "added"}],
                    created_at=now(),
                )
            )
            self.record_item(
                item, before_content=None, before_status=None, actor="user"
            )
            self.touch(project)
        return item

    def update_item(
        self,
        item_id: str,
        *,
        content: str | None,
        status: ItemStatus | None,
        group: Group | None,
        priority: Priority | None,
        reason: str | None,
    ) -> RequirementItem:
        """The only path that can confirm or reject an item. Users only."""
        item = self.owned_item(item_id)
        before_content, before_status = item.content, item.status
        if content is not None and content.strip() and content.strip() != item.content:
            item.content = content.strip()
            # Rewritten by the user: it is now their statement.
            item.source_kind = SourceKind.USER
            item.source_quote = item.content
            if status is None:
                status = ItemStatus.CONFIRMED
        if status is not None:
            item.status = status
        if group is not None:
            item.group = group
        if priority is not None:
            item.priority = priority
        item.updated_at = now()
        with self.store.transaction():
            self.store.update(item)
            self.record_item(
                item,
                before_content=before_content,
                before_status=before_status,
                actor="user",
                reason=reason,
            )
            self.touch(self.project(item.project_id))
        return item

    def revisions(self, item_id: str) -> list[ItemRevision]:
        item = self.owned_item(item_id)
        return self.store.select(
            ItemRevision, "item_id = ?", (item.id,), order="created_at"
        )

    def links(self, project_id: str) -> list[Link]:
        self.project(project_id)
        return self.store.links(project_id)

    # --- analyst --------------------------------------------------------------

    def start_analysis(self, project_id: str, brief_id: str | None = None) -> Job:
        """Run the Product Analyst on the baseline, or on one Brief snapshot.

        A Brief is a frozen copy of the baseline, so checking it is the same
        job on that copy; the findings remember which Brief version they
        checked, and drafting a new Brief never removes them.
        """
        project = self.project(project_id)
        self.ensure_idle(project_id)
        brief_version: int | None = None
        if brief_id is not None:
            brief = self.store.get(Brief, brief_id)
            if brief is None or brief.project_id != project_id:
                raise NotFound("brief")
            brief_version = brief.version
            baseline = [
                {k: item[k] for k in ("code", "group", "status", "content")}
                for item in brief.items
            ]
        else:
            baseline = [
                {
                    "code": i.code,
                    "group": i.group.value,
                    "status": i.status.value,
                    "content": i.content,
                }
                for i in self.items(project_id)
            ]
        if not baseline:
            raise Invalid("BASELINE_EMPTY", "There is nothing to analyse yet.")
        existing = self.findings(
            project_id, "scope = ?", (FindingScope.BASELINE.value,)
        )
        payload = {
            "target": "product_brief" if brief_version else "baseline",
            "baseline": baseline,
            "existing_findings": [
                {
                    "code": f.code,
                    "kind": f.kind,
                    "title": f.title,
                    "status": f.status.value,
                }
                for f in existing
            ],
        }

        async def run(ctx: JobContext) -> dict[str, Any]:
            output = await ctx.structured(
                task="analyze",
                instructions=ANALYST_PROMPT,
                payload=payload,
                schema=AnalystOutput,
            )
            return self.apply_analysis(
                project.id,
                output,
                brief_version=brief_version,
                codes={str(i["code"]) for i in baseline},
            )

        return self.jobs.start(
            project_id=project_id,
            kind=JobKind.ANALYZE,
            input={"items": len(baseline), "brief_version": brief_version},
            runner=run,
        )

    def apply_analysis(
        self,
        project_id: str,
        output: AnalystOutput,
        *,
        brief_version: int | None = None,
        codes: set[str] | None = None,
    ) -> dict[str, Any]:
        """Admit only findings tied to real baseline codes; never repeat old ones."""
        if codes is None:
            codes = {i.code for i in self.items(project_id)}
        existing = self.findings(
            project_id, "scope = ?", (FindingScope.BASELINE.value,)
        )
        added: list[str] = []
        rejected_without_evidence = 0
        repeated = 0
        with self.store.transaction():
            for raw in output.findings:
                evidence_items = [code for code in raw.evidence_items if code in codes]
                if not evidence_items:
                    rejected_without_evidence += 1
                    continue
                if raw.kind is AnalystKind.OPPORTUNITY and raw.opportunity is None:
                    rejected_without_evidence += 1
                    continue
                match = next(
                    (
                        f
                        for f in existing
                        if same_problem(
                            f.title,
                            f.problem,
                            f.kind,
                            f.kind,
                            raw.title,
                            raw.problem,
                            raw.kind.value,
                            raw.kind.value,
                        )
                    ),
                    None,
                )
                if match is not None:
                    # Raised again: keep the one finding (and the user's
                    # decision on it), but record that this Brief was checked.
                    repeated += 1
                    if brief_version is not None:
                        match.brief_version = brief_version
                        match.updated_at = now()
                        self.store.update(match)
                        added.append(match.code)
                    continue
                finding = Finding(
                    id=new_id(),
                    project_id=project_id,
                    code=self.store.next_code(project_id, "F"),
                    scope=FindingScope.BASELINE,
                    reviewer=Reviewer.ANALYST,
                    reviewers=[Reviewer.ANALYST],
                    kind=raw.kind.value,
                    severity=guard_severity(
                        raw.severity, raw.kind.value, raw.confidence
                    ),
                    title=raw.title.strip(),
                    category=raw.kind.value,
                    evidence=raw.evidence.strip(),
                    evidence_verified=True,
                    problem=raw.problem.strip(),
                    impact=raw.impact.strip(),
                    recommendation=raw.recommendation.strip(),
                    confidence=raw.confidence,
                    opportunity=(
                        raw.opportunity.model_dump(mode="json")
                        if raw.opportunity is not None
                        else None
                    ),
                    related_items=evidence_items,
                    brief_version=brief_version,
                    status=FindingStatus.OPEN,
                    verification=Verification.NOT_CHECKED,
                    created_at=now(),
                    updated_at=now(),
                )
                self.store.insert(finding)
                existing.append(finding)
                for code in evidence_items:
                    self.store.add_link(
                        project_id,
                        Link(
                            from_code=finding.code,
                            to_code=code,
                            kind="affects",
                            origin="ai",
                        ),
                    )
                added.append(finding.code)
            self.add_message(
                Message(
                    id=new_id(),
                    project_id=project_id,
                    round=self.project(project_id).round,
                    role="ai",
                    kind="analysis",
                    content=(
                        f"检查了 Product Brief v{brief_version}："
                        if brief_version
                        else ""
                    )
                    + output.summary.strip(),
                    finding_codes=added,
                    created_at=now(),
                )
            )
            self.touch(self.project(project_id))
        return {
            "added": added,
            "without_evidence": rejected_without_evidence,
            "repeated": repeated,
        }


def _default_name(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else "新项目"
    for mark in ("。", "，", ",", ".", "；", ";"):
        if mark in first:
            first = first.split(mark)[0]
    return first[:24] or "新项目"
