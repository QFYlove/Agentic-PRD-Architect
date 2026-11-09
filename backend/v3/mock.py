"""Deterministic stand-in for the five V3 model calls.

Used whenever ``ENABLE_MOCK_LLM`` is on and by every test. It reads the real
payload, so its output refers to the project's actual items, sections and
findings -- the services then apply exactly the rules they apply to a real
model. Nothing here is shown as real analysis: the app labels mock mode.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any

from backend.prd_document import PRD_COMPLETION_MARKER
from backend.providers.base import ProviderStructuredResult, ProviderTextEvent
from backend.rubric import ROLE_RUBRICS
from backend.schemas import TokenUsage
from backend.v3.models import Strict
from backend.v3.rubric import PRODUCT_DIMENSIONS

FEATURE_GOAL = "写到可以开发的程度"

#: Questions the mock asks, in priority order, by target group.
QUESTION_BANK: tuple[tuple[str, str, str, str], ...] = (
    (
        "user",
        "P0",
        "最核心的用户是谁？他们现在处在什么情况？",
        "先确定为谁设计，才能判断哪些问题最值得解决。",
    ),
    (
        "problem",
        "P0",
        "这些用户现在遇到的最大问题是什么？",
        "核心问题决定 MVP 必须包含什么。",
    ),
    (
        "scenario",
        "P0",
        "用户会在什么时候、为了完成什么事使用它？",
        "具体场景决定核心流程怎么设计。",
    ),
    (
        "alternative",
        "P1",
        "他们现在用什么方式解决这个问题？哪里不好用？",
        "了解现有方案，才能说清楚为什么换成你的产品。",
    ),
    ("goal", "P1", "上线后，你希望看到什么变化？", "产品目标决定优先级和验收方式。"),
    ("constraint", "P1", "团队、预算、时间上有哪些限制？", "约束决定 MVP 能做多大。"),
    (
        "feature",
        "P1",
        "第一版必须有哪些功能？哪些可以以后再做？",
        "范围不清会让 PRD 失去重点。",
    ),
    ("decision", "P2", "收费方式有初步想法吗？", "商业模式影响功能边界和成本控制。"),
)

GROUP_FOR_KEYWORD = (
    ("用户", "user"),
    ("学生", "user"),
    ("问题", "problem"),
    ("痛点", "problem"),
    ("限速", "problem"),
    ("场景", "scenario"),
    ("预算", "constraint"),
    ("团队", "constraint"),
    ("上线", "constraint"),
    ("支持", "feature"),
)


def _usage(payload: Any) -> TokenUsage:
    size = len(str(payload))
    return TokenUsage(
        input_tokens=size // 2, output_tokens=200, total_tokens=size // 2 + 200
    )


def _clauses(text: str) -> list[str]:
    parts = re.split(r"[。！？!?\n；;]+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 4]


class MockGateway:
    is_mock = True
    provider_name = "mock"
    model = "mock-prd-v3"

    def __init__(self, *, delay: float = 0.0, stream_delay: float = 0.0) -> None:
        self.delay = delay
        self.stream_delay = stream_delay
        #: Section titles whose generation fails (tests and E2E failure paths).
        self.fail_sections: set[str] = set()
        #: Tasks that raise; e.g. ``{"review:biz"}``.
        self.fail_tasks: set[str] = set()
        #: Overrides keyed by task, returned verbatim (tests).
        self.responses: dict[str, Any] = {}
        self.calls: list[str] = []

    async def _wait(self) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)

    async def structured(
        self,
        *,
        task: str,
        instructions: str,
        payload: dict[str, Any],
        schema: type[Strict],
        language: str,
    ) -> ProviderStructuredResult:
        self.calls.append(task)
        await self._wait()
        if task in self.fail_tasks:
            from backend.errors import RetryableProviderError

            raise RetryableProviderError("Mock failure")
        if task in self.responses:
            value = self.responses[task]
            value = value(payload) if callable(value) else value
        elif task == "explore":
            value = self._explore(payload)
        elif task == "analyze":
            value = self._analyze(payload)
        elif task == "outline":
            value = self._outline(payload)
        elif task.startswith("review:"):
            value = self._review(task.split(":", 1)[1], payload)
        elif task == "optimize":
            value = self._optimize(payload)
        elif task.startswith("repair:"):
            value = payload.get("invalid_value")
        else:  # pragma: no cover - programming error
            raise ValueError(task)
        return ProviderStructuredResult(
            value=value, usage=_usage(payload), model=self.model
        )

    async def stream(
        self,
        *,
        task: str,
        instructions: str,
        payload: dict[str, Any],
        language: str,
    ) -> AsyncIterator[ProviderTextEvent]:
        self.calls.append(task)
        section = payload.get("section", {})
        title = str(section.get("title", ""))
        if title in self.fail_sections:
            from backend.errors import ProviderOutputTruncatedError

            yield ProviderTextEvent(delta="部分内容……", model=self.model)
            raise ProviderOutputTruncatedError("Mock truncation")
        body = self._section_body(payload)
        for start in range(0, len(body), 60):
            if self.stream_delay:
                await asyncio.sleep(self.stream_delay)
            yield ProviderTextEvent(delta=body[start : start + 60], model=self.model)
        yield ProviderTextEvent(
            model=self.model, finish_reason="stop", usage=_usage(payload)
        )

    # --- explorer -------------------------------------------------------------

    def _explore(self, payload: dict[str, Any]) -> dict[str, Any]:
        baseline = payload.get("baseline", [])
        this_round = payload.get("this_round", {})
        items: list[dict[str, Any]] = []
        said: list[str] = []
        initial = str(this_round.get("initial_input") or "")
        if initial:
            clauses = _clauses(initial) or [initial.strip()]
            head, _, wanted = clauses[0].partition("支持")
            position = head.rstrip("，, ") if wanted and len(head) >= 4 else clauses[0]
            items.append(_user_item("position", position, "P0"))
            said.append(position)
            for index, feature in enumerate(re.split(r"[、，,和]", wanted)):
                if len(feature.strip()) >= 2:
                    priority = "P0" if index == 0 else "P1"
                    items.append(_user_item("feature", feature.strip(), priority))
            for clause in clauses[1:4]:
                group = next(
                    (g for k, g in GROUP_FOR_KEYWORD if k in clause), "feature"
                )
                # The first feature the user names is treated as core.
                first = group == "feature" and all(
                    i["group"] != "feature" for i in items
                )
                items.append(_user_item(group, clause, "P0" if first else "P1"))
                said.append(clause)
            items.append(
                {
                    "group": "problem",
                    "content": "用户现在需要在多个工具之间切换才能完成同一件事",
                    "status": "inferred",
                    "source_kind": "ai",
                    "priority": "P0",
                    "reason": "从你描述的功能组合推断，需要你确认",
                }
            )
            items.append(
                {
                    "group": "assumption",
                    "content": "目标用户愿意为更顺畅的体验更换现有工具",
                    "status": "assumption",
                    "source_kind": "ai",
                    "priority": "P1",
                    "reason": "产品成立的前提，目前没有证据",
                }
            )
        for answer in this_round.get("answers", []):
            text = str(answer.get("answer") or "").strip()
            if not text:
                continue
            items.append(
                _user_item(str(answer.get("group") or "feature"), text[:300], "P1")
            )
            said.append(text)
            if answer.get("group") == "constraint":
                items.append(
                    {
                        "group": "decision",
                        "content": "MVP 只做核心流程，其余功能放到 P1",
                        "status": "proposed",
                        "source_kind": "ai",
                        "priority": "P1",
                        "reason": "资源约束较紧，先保证核心价值",
                    }
                )
        supplement = str(this_round.get("supplement") or "").strip()
        if supplement:
            items.append(_user_item("feature", supplement[:300], "P1"))
            said.append(supplement)

        asked = [str(q) for q in payload.get("asked_questions", [])]
        confirmed = {b["group"] for b in baseline if b.get("status") == "confirmed"}
        limit = 2 if payload.get("depth") == "brief" else 3
        questions: list[dict[str, Any]] = []
        for focus in payload.get("focus_findings", [])[:1]:
            questions.append(
                {
                    "text": f"关于「{focus['title']}」，你打算怎么处理？",
                    "purpose": f"这条发现你已采纳：{focus['recommendation']}",
                    "target_group": "decision",
                    "priority": "P0",
                    "finding_code": focus["code"],
                }
            )
        for group, priority, text, purpose in QUESTION_BANK:
            if len(questions) >= limit:
                break
            if group in confirmed or text in asked:
                continue
            questions.append(
                {
                    "text": text,
                    "purpose": purpose,
                    "target_group": group,
                    "priority": priority,
                }
            )
        heard = "；".join(s[:30] for s in said[:2]) or "你跳过了这一轮的问题"
        return {
            "understanding": f"我记下了：{heard}。还需要和你确认的内容放在右侧。",
            "items": items,
            "questions": questions,
            "ready_for_brief": False,
        }

    # --- analyst --------------------------------------------------------------

    def _analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        baseline = payload.get("baseline", [])
        by_group: dict[str, list[str]] = {}
        for item in baseline:
            by_group.setdefault(item["group"], []).append(item["code"])
        any_code = [baseline[0]["code"]] if baseline else []
        findings: list[dict[str, Any]] = []
        if not by_group.get("goal"):
            findings.append(
                {
                    "kind": "gap",
                    "title": "产品目标还没有明确",
                    "severity": "should_fix",
                    "evidence_items": by_group.get("position", any_code)[:2],
                    "evidence": "需求基线里有产品定位，但没有任何产品目标条目。",
                    "problem": (
                        "没有目标，就无法判断 MVP 范围是否合适，也无法写验收标准。"
                    ),
                    "impact": "PRD 的优先级和验收标准会缺少依据。",
                    "recommendation": "补充一到两条上线后希望看到的变化。",
                    "confidence": 0.8,
                }
            )
        if by_group.get("constraint") and by_group.get("feature"):
            findings.append(
                {
                    "kind": "conflict",
                    "title": "功能范围可能超出资源约束",
                    "severity": "should_fix",
                    "evidence_items": by_group["constraint"][:1]
                    + by_group["feature"][:2],
                    "evidence": "约束条目限制了资源，功能条目却没有做取舍。",
                    "problem": "按当前范围，约束内可能无法完成全部功能。",
                    "impact": "范围不收敛会让 PRD 的 P0 失去意义。",
                    "recommendation": "确认哪些功能是 P0，其余放到 P1。",
                    "confidence": 0.6,
                }
            )
        if by_group.get("scenario"):
            findings.append(
                {
                    "kind": "scenario",
                    "title": "核心场景缺少失败处理",
                    "severity": "optional",
                    "evidence_items": by_group["scenario"][:1],
                    "evidence": "场景条目只描述了顺利完成的情况。",
                    "problem": "没有说明失败或中断时用户会怎样。",
                    "impact": "异常处理章节会缺少依据。",
                    "recommendation": "补充最常见的一种失败情况和期望的处理方式。",
                    "confidence": 0.7,
                }
            )
        if by_group.get("problem"):
            findings.append(
                {
                    "kind": "opportunity",
                    "title": "把多步操作合并为一步",
                    "severity": "optional",
                    "evidence_items": by_group["problem"][:1],
                    "evidence": "用户问题条目提到需要在多个工具之间切换。",
                    "problem": "现有方案要求用户自己串联多个步骤。",
                    "impact": "合并后可以成为主要差异点。",
                    "recommendation": "评估把最常见的两步合成一个操作的可行性。",
                    "confidence": 0.5,
                    "opportunity": {
                        "user_problem": "需要在多个工具之间切换",
                        "current_solution": "用户手动在两个工具间搬运结果",
                        "shortfall": "步骤多、容易出错、等待时间长",
                        "value": "一次操作完成，减少等待和出错",
                        "cost": "需要打通两个环节的数据，开发量中等",
                        "assumptions": ["用户最常见的路径确实是这两步连用"],
                    },
                }
            )
        return {
            "summary": (
                f"检查了 {len(baseline)} 条需求，"
                f"发现 {len(findings)} 个值得处理的问题。"
            ),
            "findings": findings,
        }

    # --- generator --------------------------------------------------------------

    def _outline(self, payload: dict[str, Any]) -> dict[str, Any]:
        brief = payload.get("brief", {})
        by_title = {
            s["title"]: s.get("item_codes", []) for s in brief.get("sections", [])
        }

        def codes(*titles: str) -> list[str]:
            return [c for t in titles for c in by_title.get(t, [])]

        features = codes("核心功能范围")
        texts = {
            str(item["code"]): str(item["content"]) for item in brief.get("items", [])
        }
        sections: list[dict[str, Any]] = [
            _entry(
                "1",
                "产品概述",
                1,
                "说明产品是什么、为谁解决什么问题",
                codes("产品定位", "目标用户", "产品目标"),
            ),
            _entry(
                "2",
                "用户问题与场景",
                1,
                "说明用户的问题和典型场景",
                codes("用户问题", "核心使用场景", "现有解决方式"),
            ),
            _entry(
                "3",
                "MVP 范围",
                1,
                "列出功能和优先级",
                features + codes("产品约束", "已确认决策"),
            ),
            _entry("4", "功能需求", 1, "按优先级描述功能", []),
        ]
        for index, code in enumerate(features[:3], start=1):
            sections.append(
                _entry(
                    f"4.{index}",
                    texts.get(code, f"功能 {index}")[:18],
                    2,
                    FEATURE_GOAL,
                    [code],
                    ["3"],
                )
            )
        sections += [
            _entry("5", "异常处理", 1, "列出失败和边界情况", features[:2], ["4"]),
            _entry("6", "验收标准", 1, "可测试的验收条件", features, ["4", "5"]),
            _entry(
                "7",
                "假设与待确认事项",
                1,
                "列出未确认的信息",
                codes("假设", "待确认事项"),
            ),
        ]
        return {"title": "产品需求文档", "sections": sections}

    def _section_body(self, payload: dict[str, Any]) -> str:
        section = payload.get("section", {})
        title = str(section.get("title", ""))
        items = payload.get("items", [])

        def line(item: dict[str, Any]) -> str:
            label = {
                "confirmed": "[已确认]",
                "inferred": "[假设]",
                "assumption": "[假设]",
                "proposed": "[建议]",
                "open": "[待确认]",
            }.get(str(item.get("status")), "")
            return f"- {item.get('content')} {label}".rstrip()

        listed = "\n".join(line(i) for i in items) or "- 本节内容待补充 [待确认]"
        if title == "功能需求":
            body = "按优先级排列。P0 功能写到可以直接开发的程度，P1 只写核心流程。"
        elif section.get("goal") == FEATURE_GOAL:
            content = items[0]["content"] if items else title
            body = (
                f"{content}。\n\n"
                "1. 用户在首页发起操作。\n"
                "2. 系统校验输入并展示结果预览。\n"
                "3. 用户确认后任务进入处理队列。\n"
                "4. 处理完成后通知用户。\n\n"
                "- 同一用户同时最多 3 个处理中的任务 [建议]。"
            )
        elif title == "异常处理":
            body = (
                "- 输入无法识别：提示原因，不创建任务。\n"
                "- 任务长时间没有响应：任务标记为失败。\n"
                "- 存储空间不足：暂停任务并提示清理空间。"
            )
        elif title == "验收标准":
            body = (
                "1. 核心流程可以完成。\n"
                "2. 处理完成后用户收到通知。\n"
                "3. 输入无法识别时看到明确的错误提示。"
            )
        elif title == "MVP 范围":
            status_text = {"confirmed": "已确认", "open": "待确认"}
            body = (
                "| 内容 | 优先级 | 状态 |\n| --- | --- | --- |\n"
                + "\n".join(
                    f"| {i.get('content')} | {i.get('priority', 'P1')} | "
                    f"{status_text.get(str(i.get('status')), '假设')} |"
                    for i in items
                )
                if items
                else listed
            )
        else:
            body = listed
        return f"{body}\n\n{PRD_COMPLETION_MARKER}"

    # --- reviewers ----------------------------------------------------------------

    def _review(self, reviewer: str, payload: dict[str, Any]) -> dict[str, Any]:
        sections = payload.get("sections", [])
        bodies = "\n".join(str(s.get("body", "")) for s in sections)

        def num_of(phrase: str) -> str:
            for s in sections:
                if phrase in str(s.get("body", "")):
                    return str(s.get("num"))
            return ""

        findings: list[dict[str, Any]] = []
        if reviewer == "tech" and "长时间没有响应" in bodies:
            findings.append(
                _review_finding(
                    "超时时长没有定义",
                    "should_fix",
                    "reliability",
                    num_of("长时间没有响应"),
                    "「长时间没有响应」",
                    "没有给出超时阈值，无法开发和测试，也没有说明失败后是否可以重试。",
                    "开发会各自猜一个时长，测试无法验收。",
                    "给出超时时长和失败后的重试规则，并同步到验收标准。",
                )
            )
            # Outside this reviewer's domain: the aggregator drops it.
            findings.append(
                _review_finding(
                    "收费模式不清楚",
                    "should_fix",
                    "business_model",
                    "",
                    "「核心流程」",
                    "没有说明如何收费。",
                    "",
                    "补充收费方式。",
                )
            )
        if reviewer == "ux" and "长时间没有响应" in bodies:
            findings.append(
                _review_finding(
                    "超时时长没有定义，用户不知道要等多久",
                    "should_fix",
                    "recovery",
                    num_of("长时间没有响应"),
                    "「任务长时间没有响应」",
                    "失败前用户看不到进度，失败后也不知道下一步。",
                    "用户会反复刷新或放弃。",
                    "失败时提示原因，并提供重试入口。",
                )
            )
        if reviewer == "product" and "核心流程可以完成" in bodies:
            findings.append(
                _review_finding(
                    "验收标准无法测试",
                    "must_fix",
                    "requirement_gap",
                    num_of("核心流程可以完成"),
                    "「核心流程可以完成」",
                    "「核心流程可以完成」没有可观察的结果，无法判断是否通过。",
                    "上线前无法验收 P0 功能。",
                    "为每个 P0 功能写出输入、操作和可观察的结果。",
                )
            )
        resolutions = []
        for previous in payload.get("previous_findings", []):
            quote = _quoted(str(previous.get("evidence", "")))
            still = bool(quote) and quote in bodies
            resolutions.append(
                {
                    "finding_code": previous["finding_code"],
                    "status": "unresolved" if still else "resolved",
                    "note": "原文仍然存在" if still else "原文已修改",
                }
            )
        dimensions = (
            PRODUCT_DIMENSIONS if reviewer == "product" else ROLE_RUBRICS[reviewer]
        )
        score = 3 if findings else 4
        return {
            "reviewer": reviewer,
            "summary": (
                f"整体结构完整，发现 {len(findings)} 个需要处理的问题。"
                if findings
                else "在本角色的范围内没有发现需要处理的问题。"
            ),
            "strengths": ["章节结构清楚", "未确认信息有标注"],
            "risks": [f["title"] for f in findings][:2],
            "blocking": any(f["severity"] == "must_fix" for f in findings),
            "dimension_scores": [
                {
                    "dimension": d.id,
                    "score": score,
                    "rationale": f"{d.label_zh}：{score}/5",
                }
                for d in dimensions
            ],
            "findings": findings,
            "resolutions": resolutions,
        }

    # --- optimizer ----------------------------------------------------------------

    def _optimize(self, payload: dict[str, Any]) -> dict[str, Any]:
        sections = {s["code"]: s for s in payload.get("sections", [])}
        changes = []
        declined = []
        bodies: dict[str, str] = {}
        for finding in payload.get("findings", []):
            codes = [c for c in finding.get("sections", []) if c in sections]
            quote = _quoted(str(finding.get("evidence", "")))
            if not codes or not quote:
                declined.append(
                    {
                        "finding_code": finding["finding_code"],
                        "reason": "找不到对应的原文",
                    }
                )
                continue
            code = codes[0]
            body = bodies.get(code, str(sections[code]["body"]))
            fix = str(finding.get("user_note") or finding["recommendation"]).rstrip(
                "。"
            )
            bodies[code] = body.replace(quote, f"{fix} [建议]")
            changes.append(
                {
                    "change_type": "UPDATE",
                    "section": code,
                    "reason": f"处理 {finding['finding_code']}：{finding['title']}",
                    "after": bodies[code],
                    "finding_codes": [finding["finding_code"]],
                    "affected_sections": [],
                    "must_preserve": [],
                }
            )
        return {
            "objective": "只修改已采纳的问题，其余内容保持不变。",
            "changes": changes,
            "declined": declined,
        }


def _user_item(group: str, text: str, priority: str) -> dict[str, Any]:
    return {
        "group": group,
        "content": text,
        "status": "inferred",
        "source_kind": "user",
        "source_quote": text,
        "priority": priority,
        "reason": "来自你的描述，确认后生效",
    }


def _entry(
    num: str,
    title: str,
    level: int,
    goal: str,
    item_codes: list[str],
    depends: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "num": num,
        "title": title,
        "level": level,
        "goal": goal,
        "contents": [goal],
        "item_codes": item_codes,
        "depends": depends or [],
        "open_points": [],
    }


def _review_finding(
    title: str,
    severity: str,
    category: str,
    section: str,
    evidence: str,
    problem: str,
    impact: str,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "severity": severity,
        "category": category,
        "section": section,
        "evidence": evidence,
        "problem": problem,
        "impact": impact,
        "recommendation": recommendation,
        "confidence": 0.8,
        "related_items": [],
    }


def _quoted(evidence: str) -> str:
    match = re.search(r"「(.+?)」", evidence)
    return match.group(1) if match else ""
