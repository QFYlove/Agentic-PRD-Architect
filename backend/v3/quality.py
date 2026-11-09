"""The four quality views (definition 8.2), computed by code from stored data.

None of them is a model's opinion and none is combined with the others into a
single score. When there is nothing to measure, the value is ``None`` and the
reason says so; no figure is filled in.
"""

from __future__ import annotations

from typing import Any

from backend.prd_quality import check_prd
from backend.v3.base import Base
from backend.v3.models import (
    CORE_GROUPS,
    GROUPS,
    Finding,
    FindingStatus,
    Group,
    ItemStatus,
    Priority,
    SectionStatus,
    Severity,
)
from backend.v3.rules import markdown_document

UNSETTLED = (
    FindingStatus.OPEN,
    FindingStatus.ACCEPTED,
    FindingStatus.MODIFIED,
    FindingStatus.DEFERRED,
    FindingStatus.STALE,
)


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


class Quality(Base):
    def compute(self, project_id: str) -> dict[str, Any]:
        project = self.project(project_id)
        items = self.items(project_id)
        sections = self.sections(project_id)
        findings = self.findings(project_id)
        written = [s for s in sections if s.body.strip()]

        # 1. Document quality: completion and deterministic structure checks.
        if written:
            report = check_prd(
                markdown_document(
                    project.doc_title or project.name,
                    [(s.level, s.num, s.title, s.body) for s in sections],
                )
            )
            issues = [i for i in report.issues if i.code != "missing_section"]
            errors = sum(i.severity == "error" for i in issues)
            warnings = sum(i.severity == "warning" for i in issues)
            done = sum(s.status is SectionStatus.DONE for s in sections)
            document: dict[str, Any] = {
                "value": _clamp(100 * done / len(sections) - 5 * errors - 2 * warnings),
                "formula": "完成章节占比 × 100 − 5 × 结构错误 − 2 × 结构提醒",
                "details": [
                    f"{done}/{len(sections)} 个章节已完成",
                    f"{report.unlabeled_figures} 处数字未标注来源",
                    f"{errors} 个结构错误，{warnings} 个结构提醒",
                ],
                "issues": [i.model_dump(mode="json") for i in issues[:20]],
            }
        else:
            document = {"value": None, "reason": "还没有 PRD 正文", "details": []}

        # 2. Requirement maturity: how much of the baseline the user confirmed.
        if items:
            confirmed = [i for i in items if i.status is ItemStatus.CONFIRMED]
            core = [g for g in CORE_GROUPS if any(i.group is g for i in confirmed)]
            maturity: dict[str, Any] = {
                "value": _clamp(
                    50 * len(core) / len(CORE_GROUPS) + 50 * len(confirmed) / len(items)
                ),
                "formula": "50 × 已确认的核心分组占比 + 50 × 已确认条目占比",
                "details": [
                    f"核心信息 {len(core)}/{len(CORE_GROUPS)} 组已确认",
                    f"{len(confirmed)}/{len(items)} 条需求已确认",
                ],
                "missing_core": [GROUPS[g][0] for g in CORE_GROUPS if g not in core],
            }
        else:
            maturity = {"value": None, "reason": "需求基线为空", "details": []}

        # 3. Implementation readiness: P0 coverage, open points, blockers.
        blockers = [
            f
            for f in findings
            if f.severity is Severity.MUST_FIX and f.status in UNSETTLED
        ]
        p0 = [
            i for i in items if i.group is Group.FEATURE and i.priority is Priority.P0
        ]
        if not written:
            readiness: dict[str, Any] = {
                "value": None,
                "reason": "还没有 PRD 正文",
                "details": [],
            }
        elif not p0:
            # Coverage of nothing is not 100%: without P0 features there is
            # no basis for the number, so none is shown.
            readiness = {
                "value": None,
                "reason": "需求里没有标为 P0 的功能，无法判断覆盖情况",
                "details": [f"{len(blockers)} 个未解决的必须修改问题"],
            }
        else:
            covered_codes = {code for s in written for code in s.item_codes}
            covered = [i for i in p0 if i.code in covered_codes]
            tbd = sum(s.body.count("[待确认]") for s in written)
            readiness = {
                "value": _clamp(
                    100 * len(covered) / len(p0) - 15 * len(blockers) - 2 * tbd
                ),
                "formula": (
                    "100 × P0 功能覆盖率 − 15 × 未解决阻塞问题 − 2 × 正文待确认项"
                ),
                "details": [
                    f"P0 功能 {len(covered)}/{len(p0)} 项写入正文",
                    f"{len(blockers)} 个未解决的必须修改问题",
                    f"正文中 {tbd} 处待确认",
                ],
            }

        # 4. Open risks and blockers: counts only, never a score.
        def count(predicate: Any) -> int:
            return sum(1 for f in findings if predicate(f))

        risks = {
            "value": None,
            "blocking": len(blockers),
            "open_findings": count(lambda f: f.status is FindingStatus.OPEN),
            "stale_findings": count(lambda f: f.status is FindingStatus.STALE),
            "deferred_findings": count(lambda f: f.status is FindingStatus.DEFERRED),
            "open_items": sum(i.status is ItemStatus.OPEN for i in items),
            "assumptions": sum(i.status is ItemStatus.ASSUMPTION for i in items),
            "unverified_evidence": count(
                lambda f: not f.evidence_verified and f.status in UNSETTLED
            ),
        }
        return {
            "document_quality": document,
            "requirement_maturity": maturity,
            "implementation_readiness": readiness,
            "risks": risks,
        }


def blocking(findings: list[Finding]) -> int:
    return sum(
        1 for f in findings if f.severity is Severity.MUST_FIX and f.status in UNSETTLED
    )
