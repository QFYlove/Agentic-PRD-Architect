"""Anonymised human-review packages, independent submissions, adjudication.

Layout under ``review/<batch>/`` (local, git-ignored):

  package/                       what reviewers receive -- nothing else
    README.md                    instructions and the blinding caveat
    order.json                   randomised presentation order
    docs/<review_id>/
      requirement.md             frozen input of the case
      prd.md                     the document
      scoresheet.yaml            empty sheet for R/C/dimension judgments
  private/
    mapping.json                 review_id -> doc_id / case / condition labels
  submissions/<reviewer>/<review_id>.yaml    written once = locked
  adjudication/<review_id>.yaml              final decision on disagreements

The package never contains condition labels, run paths, judge output, model
identifiers, scores, or existing decisions. Review ids are random and
unrelated to judge-side ``doc_id``s.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from prd_benchmark._yaml import dump_yaml, load_yaml
from prd_benchmark.artifacts import (
    ArtifactExistsError,
    BatchLayout,
    read_json,
    write_json_once,
    write_text_once,
)
from prd_benchmark.cases import (
    CALIBRATION_BATCH_PREFIX,
    CALIBRATION_CASES_DIR,
    Case,
    load_cases,
)
from prd_benchmark.evidence import EvidenceIndex
from prd_benchmark.judge import DIMENSIONS, ItemJudgment, JudgeOutput
from prd_benchmark.pipeline import BlindEntry, load_blind_map

_ID_ALPHABET = "bcdfghjkmnpqrstvwxz23456789"
_REVIEWER = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
#: Strings that must never appear anywhere in a review package.
FORBIDDEN_IN_PACKAGE = (
    "B.best",
    "B.last",
    "B.v1",
    "best_version",
    "condition",
    "doc_id",
    "judge",
    "deepseek",
    "claude",
    "model",
    "/A/",
    "/B/",
)

README = """# PRD 人工评审包

请独立完成评审，评审期间不要与其他评审者讨论，也不要查看任何自动评分结果或报告。

每个文件夹是一份待评文档，包含：

- `requirement.md`：PRD 作者收到的原始需求输入；
- `prd.md`：待评的 PRD；
- `scoresheet.yaml`：评分表。逐条填写 R 条目和 C 条目的判定（covered / partial /
  missing / contradicted）、引用的原文和理由，以及五个维度的 0–4 锚点。评分规则见
  仓库中的 `rubric.md`（只读，不需要提交）。

请按 `order.json` 的顺序评审。

**盲化提示：** 文件名、路径和文件内容中都不包含生成方式或模型信息，但文档的篇幅、结构
和写作风格仍可能让你猜到它的来源。这种情况下请照常评分；评分表末尾有一栏可以记录你的
猜测和把握度，用于估计盲化效果。匿名评审不能保证完全盲化。

提交方式：把填好的 `scoresheet.yaml` 交给协调人。提交后即锁定，不能修改；如需更正，
在裁定阶段提出。
"""


@dataclass(frozen=True)
class ReviewEntry:
    review_id: str
    doc_id: str
    case_id: str
    labels: tuple[str, ...]


def _blank_item() -> dict[str, Any]:
    # contradiction_kind (general / internal) and hard_constraint (an H id)
    # are filled only for a contradicted verdict.
    return {
        "verdict": None,
        "contradiction_kind": None,
        "hard_constraint": None,
        "quotes": [],
        "rationale": None,
    }


def _scoresheet(case: Case) -> dict[str, Any]:
    return {
        "review_id": None,
        "reviewer": None,
        "items": {item.id: _blank_item() for item in case.required_items},
        "clarifications": {item.id: _blank_item() for item in case.clarifications},
        "dimensions": {name: {"anchor": None, "notes": None} for name in DIMENSIONS},
        "critical_defects": [],
        "blinding_guess": {"guess": None, "confidence_0_to_1": None},
    }


def _requirement(case: Case) -> str:
    frozen = case.frozen_input
    parts = [
        "# 需求输入",
        "## 需求描述",
        frozen.user_idea,
        "## 目标用户",
        frozen.target_audience or "（未提供）",
        "## 约束",
        frozen.user_constraints or "（未提供）",
    ]
    return "\n\n".join(parts) + "\n"


def export_review_package(
    layout: BatchLayout,
    cases: dict[str, Case],
    *,
    rng: secrets.SystemRandom | None = None,
) -> list[ReviewEntry]:
    """Write a new package; refuses if one already exists for the batch."""
    rng = rng or secrets.SystemRandom()
    package = layout.review / "package"
    if package.exists():
        raise ArtifactExistsError(f"review package already exists: {package}")
    blinds = {b.doc_id: b for b in load_blind_map(layout)}
    entries: list[ReviewEntry] = []
    used: set[str] = set()
    for blind in blinds.values():
        review_id = ""
        while not review_id or review_id in used:
            # No vowels: an id can never spell a label such as "best" or "last".
            review_id = "r-" + "".join(rng.choice(_ID_ALPHABET) for _ in range(8))
        used.add(review_id)
        entries.append(
            ReviewEntry(review_id, blind.doc_id, blind.case_id, tuple(blind.labels))
        )
    order = [e.review_id for e in entries]
    rng.shuffle(order)
    by_id = {e.review_id: e for e in entries}
    for review_id in order:
        entry = by_id[review_id]
        blind = blinds[entry.doc_id]
        case = cases[entry.case_id]
        folder = package / "docs" / review_id
        write_text_once(folder / "requirement.md", _requirement(case))
        prd = (layout.runs / blind.path).read_text(encoding="utf-8")
        write_text_once(folder / "prd.md", prd)
        sheet = _scoresheet(case)
        sheet["review_id"] = review_id
        write_text_once(folder / "scoresheet.yaml", dump_yaml(sheet))
    write_text_once(package / "README.md", README)
    write_json_once(package / "order.json", {"order": order})
    write_json_once(
        layout.review / "private" / "mapping.json",
        {
            "note": "Do not give this file to reviewers.",
            "entries": [
                {
                    "review_id": e.review_id,
                    "doc_id": e.doc_id,
                    "case_id": e.case_id,
                    "labels": list(e.labels),
                }
                for e in entries
            ],
        },
    )
    return entries


def package_leaks(layout: BatchLayout, entries: list[ReviewEntry]) -> list[str]:
    """Paths and texts in the package that could reveal condition or judge info.

    PRD bodies are excluded from the substring check (a generated document may
    legitimately mention "model"); their *paths* are still checked.
    """
    package = layout.review / "package"
    leaks: list[str] = []
    doc_ids = {e.doc_id for e in entries}
    for path in package.rglob("*"):
        relative = str(path.relative_to(package))
        for needle in ("/A/", "/B/", "best", "last", "v1"):
            if needle in f"/{relative}/":
                leaks.append(f"path {relative} contains {needle}")
        if path.is_dir() or path.name == "prd.md":
            continue
        text = path.read_text(encoding="utf-8")
        if path.name in {"requirement.md"}:
            checks: tuple[str, ...] = ("B.best", "B.last", "B.v1", "doc_id", "judge")
        else:
            checks = FORBIDDEN_IN_PACKAGE
        for needle in checks:
            if needle.lower() in text.lower():
                leaks.append(f"{relative} contains {needle!r}")
        for doc_id in doc_ids:
            if doc_id in text:
                leaks.append(f"{relative} contains a judge doc_id")
    return sorted(set(leaks))


def submit_review(
    layout: BatchLayout, reviewer: str, review_id: str, sheet_path: Path
) -> Path:
    """Copy a filled scoresheet into ``submissions``; written once = locked."""
    if not _REVIEWER.fullmatch(reviewer):
        raise ValueError(f"bad reviewer id {reviewer!r}")
    _require_role(layout, reviewer, ("reviewer_a", "reviewer_b"))
    sheet = load_yaml(sheet_path)
    if not isinstance(sheet, dict) or sheet.get("review_id") != review_id:
        raise ValueError("scoresheet review_id does not match")
    target = layout.review / "submissions" / reviewer / f"{review_id}.yaml"
    write_text_once(target, dump_yaml({**sheet, "reviewer": reviewer}))
    return target


def disagreements(layout: BatchLayout, review_id: str) -> dict[str, dict[str, Any]]:
    """Item and dimension fields on which locked submissions differ."""
    sheets = [
        load_yaml(p)
        for p in sorted((layout.review / "submissions").glob(f"*/{review_id}.yaml"))
    ]
    if len(sheets) < 2:
        return {}
    found: dict[str, dict[str, Any]] = {}
    for section, attr in (
        ("items", "verdict"),
        ("items", "contradiction_kind"),
        ("items", "hard_constraint"),
        ("clarifications", "verdict"),
        ("clarifications", "contradiction_kind"),
        ("clarifications", "hard_constraint"),
        ("dimensions", "anchor"),
    ):
        keys = set().union(*(s.get(section, {}) for s in sheets))
        for key in sorted(keys):
            values = {
                s["reviewer"]: s.get(section, {}).get(key, {}).get(attr) for s in sheets
            }
            if len(set(map(json.dumps, values.values()))) > 1:
                suffix = "" if attr in {"verdict", "anchor"} else f".{attr}"
                found[f"{section}.{key}{suffix}"] = values
    criticals = {s["reviewer"]: _critical_rules(s) for s in sheets}
    if len({tuple(v) for v in criticals.values()}) > 1:
        found["critical_defects"] = criticals
    return found


def _critical_rules(sheet: dict[str, Any]) -> list[str]:
    return sorted({str(d.get("rule_id")) for d in sheet.get("critical_defects") or []})


def adjudicate(
    layout: BatchLayout, review_id: str, adjudicator: str, decisions: dict[str, Any]
) -> Path:
    """Record the final decision for every disagreement; written once."""
    _require_role(layout, adjudicator, ("adjudicator",))
    open_points = disagreements(layout, review_id)
    missing = sorted(set(open_points) - set(decisions))
    if missing:
        raise ValueError(f"undecided disagreements: {missing}")
    target = layout.review / "adjudication" / f"{review_id}.yaml"
    write_text_once(
        target,
        dump_yaml(
            {
                "review_id": review_id,
                "adjudicator": adjudicator,
                "disagreements": open_points,
                "decisions": decisions,
            }
        ),
    )
    return target


# --- human calibration (P91, P92) ---------------------------------------------
#
# A calibration batch (id ``cal-*``) holds the fixed documents of
# ``calibration_set/``; nothing is generated. Its blind map has the same shape
# as a Pilot batch's, so the review export and the manual judge work unchanged.
# Order enforced in code: roles assigned -> reviewers A and B submit (locked)
# -> judge imports allowed -> adjudication -> comparison.

ROLES = ("judge_operator", "reviewer_a", "reviewer_b", "adjudicator")
CALIBRATION_LABEL = "calibration"


def is_calibration(layout: BatchLayout) -> bool:
    return layout.batch_id.startswith(CALIBRATION_BATCH_PREFIX)


def roles_file(layout: BatchLayout) -> Path:
    return layout.review / "roles.yaml"


def load_roles(layout: BatchLayout) -> dict[str, str] | None:
    path = roles_file(layout)
    return load_yaml(path) if path.exists() else None


def assign_roles(layout: BatchLayout, **people: str) -> Path:
    """Record who does what, once. Four different people are required."""
    if set(people) != set(ROLES):
        raise ValueError(f"roles must be exactly {ROLES}")
    for role, person in people.items():
        if not _REVIEWER.fullmatch(person):
            raise ValueError(f"bad id for {role}: {person!r}")
    if len(set(people.values())) != len(ROLES):
        raise ValueError("the four roles must be held by four different people")
    path = roles_file(layout)
    write_text_once(path, dump_yaml({role: people[role] for role in ROLES}))
    return path


def _require_role(layout: BatchLayout, person: str, allowed: tuple[str, ...]) -> None:
    roles = load_roles(layout)
    if roles is None:
        if is_calibration(layout):
            raise ValueError("calibration batch has no roles.yaml; assign roles first")
        return
    if person not in {roles[role] for role in allowed}:
        raise ValueError(f"{person!r} does not hold the role {' / '.join(allowed)}")


def stage_calibration_batch(
    output_root: Path, batch_id: str, cases_dir: Path = CALIBRATION_CASES_DIR
) -> list[BlindEntry]:
    """Copy the fixed calibration documents into a new ``cal-*`` batch."""
    if not batch_id.startswith(CALIBRATION_BATCH_PREFIX):
        raise ValueError(f"calibration batch ids start with {CALIBRATION_BATCH_PREFIX}")
    layout = BatchLayout(output_root, batch_id)
    if layout.runs.exists():
        raise ArtifactExistsError(f"batch {batch_id} already exists")
    case_ids = {case.id for case in load_cases(cases_dir)}
    documents = sorted((cases_dir.parent / "documents").glob("*.md"))
    entries: list[BlindEntry] = []
    for path in documents:
        case_id = path.name[: len("PQB-P00")]
        if case_id not in case_ids:
            raise ValueError(f"{path.name} names no calibration case")
        text = path.read_text(encoding="utf-8")
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        relative = f"{case_id}/CAL/{path.name}"
        write_text_once(layout.runs / relative, text)
        digest = hashlib.sha256(f"cal:{case_id}:{sha}".encode()).hexdigest()
        entries.append(
            BlindEntry(f"d-{digest[:10]}", case_id, sha, [CALIBRATION_LABEL], relative)
        )
    entries.sort(key=lambda e: e.doc_id)
    write_json_once(
        layout.scores / "blind_map.json",
        {"seed": 0, "documents": [asdict(e) for e in entries]},
    )
    return entries


def _mapping(layout: BatchLayout) -> list[dict[str, Any]]:
    data = read_json(layout.review / "private" / "mapping.json")
    return list(data["entries"])


def _submission(layout: BatchLayout, reviewer: str, review_id: str) -> Path:
    return layout.review / "submissions" / reviewer / f"{review_id}.yaml"


def calibration_judge_blockers(
    layout: BatchLayout, doc_id: str, operator: str
) -> list[str]:
    """For ``cal-*`` batches: the judge may only be run after A and B locked
    their scoresheets, and only by the assigned judge operator."""
    if not is_calibration(layout):
        return []
    roles = load_roles(layout)
    if roles is None:
        return ["calibration batch has no roles.yaml"]
    blockers: list[str] = []
    if operator != roles["judge_operator"]:
        blockers.append(f"operator {operator!r} is not the assigned judge operator")
    if not (layout.review / "private" / "mapping.json").exists():
        return [*blockers, "no human review package exported yet"]
    review_ids = [e["review_id"] for e in _mapping(layout) if e["doc_id"] == doc_id]
    for review_id in review_ids:
        for role in ("reviewer_a", "reviewer_b"):
            if not _submission(layout, roles[role], review_id).exists():
                blockers.append(f"{role} has not submitted {review_id}")
    if not review_ids:
        blockers.append("document is not in the human review package")
    return blockers


def final_human_sheet(layout: BatchLayout, review_id: str) -> dict[str, Any]:
    """Reviewer A's sheet with every disagreement replaced by the adjudication."""
    roles = load_roles(layout)
    if roles is None:
        raise ValueError("no roles.yaml")
    paths = [
        _submission(layout, roles[r], review_id) for r in ("reviewer_a", "reviewer_b")
    ]
    if not all(p.exists() for p in paths):
        raise ValueError(f"{review_id}: both reviewers must submit first")
    sheet: dict[str, Any] = load_yaml(paths[0])
    open_points = disagreements(layout, review_id)
    if open_points:
        path = layout.review / "adjudication" / f"{review_id}.yaml"
        if not path.exists():
            raise ValueError(f"{review_id}: disagreements are not adjudicated")
        decisions = load_yaml(path)["decisions"]
        for key, value in decisions.items():
            if key == "critical_defects":
                sheet["critical_defects"] = [{"rule_id": r} for r in value]
                continue
            section, item, *attr = key.split(".")
            field_name = (
                attr[0]
                if attr
                else ("anchor" if section == "dimensions" else "verdict")
            )
            sheet[section][item][field_name] = value
    return sheet


def _judge_outputs(
    layout: BatchLayout, doc_id: str, passes: int
) -> list[JudgeOutput | None]:
    outputs: list[JudgeOutput | None] = []
    for judge_pass in range(1, passes + 1):
        path = layout.judge_file(doc_id, judge_pass)
        raw = read_json(path).get("output") if path.exists() else None
        outputs.append(JudgeOutput.model_validate(raw) if raw is not None else None)
    return outputs


def _judgments(output: JudgeOutput | None) -> dict[str, ItemJudgment]:
    if output is None:
        return {}
    return {j.item_id: j for j in (*output.items, *output.clarifications)}


def _human_items(sheet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {**sheet.get("items", {}), **sheet.get("clarifications", {})}


def _cell(judgment: ItemJudgment | None, missing: str) -> str:
    return judgment.verdict if judgment is not None else missing


def calibration_comparison(
    layout: BatchLayout, cases: dict[str, Case], *, passes: int
) -> str:
    """Item-by-item human (adjudicated) vs judge table; written once.

    Counts are agreements on these two documents only. They are not an
    accuracy or agreement rate for the judge in general.
    """
    lines = [
        f"# Judge 校准对照表（{layout.batch_id}）",
        "",
        "人工结果为两名评审者独立提交、分歧经裁定后的结果；"
        "Judge 结果逐轮列出，不取平均。"
        "下列计数只描述这两份校准文档上的逐项对照，**不是 Judge 的准确率或一致率**，"
        "也不能外推到 Pilot 文档。",
        "",
    ]
    for entry in sorted(_mapping(layout), key=lambda e: e["case_id"]):
        case = cases[entry["case_id"]]
        sheet = final_human_sheet(layout, entry["review_id"])
        human = _human_items(sheet)
        outputs = _judge_outputs(layout, entry["doc_id"], passes)
        judged = [_judgments(o) for o in outputs]
        missing = ["（缺失/无效）" if o is None else "（未判定）" for o in outputs]
        blind = next(b for b in load_blind_map(layout) if b.doc_id == entry["doc_id"])
        document = (layout.runs / blind.path).read_text(encoding="utf-8")
        index = EvidenceIndex(document)
        header = " | ".join(f"Judge 第 {n} 轮" for n in range(1, passes + 1))
        lines += [f"## {case.id} {case.title}", ""]

        # 1. Coverage and clarifications.
        lines += [
            "### 1. 覆盖判定（R、C 条目）",
            "",
            f"| 条目 | 核心 | 人工 | {header} | 各轮与人工一致 |",
            "|---|---|---|" + "---|" * passes + "---|",
        ]
        agree = total = 0
        core = {i.id for i in case.required_items if i.core} | {
            c.id for c in case.clarifications if c.core
        }
        ids = [i.id for i in case.required_items] + [c.id for c in case.clarifications]
        for item_id in ids:
            human_verdict = human.get(item_id, {}).get("verdict")
            cells = [_cell(j.get(item_id), missing[n]) for n, j in enumerate(judged)]
            matches = [c == human_verdict for c in cells]
            agree += sum(matches)
            total += len(matches)
            lines.append(
                f"| {item_id} | {'是' if item_id in core else ''} | {human_verdict} | "
                + " | ".join(cells)
                + f" | {sum(matches)}/{len(matches)} |"
            )
        lines += ["", f"逐项逐轮相同：{agree}/{total}。", ""]

        # 2. Contradictions (kind and hard-constraint attribution).
        lines += [
            "### 2. 矛盾判定",
            "",
            f"| 条目 | 人工（类别 / H） | {header} |",
            "|---|---|" + "---|" * passes,
        ]
        rows = 0
        for item_id in ids:
            h = human.get(item_id, {})
            flagged = h.get("verdict") == "contradicted" or any(
                (
                    j.get(item_id) is not None
                    and (
                        j[item_id].verdict == "contradicted"
                        or j[item_id].hard_constraint_claim is not None
                    )
                )
                for j in judged
            )
            if not flagged:
                continue
            rows += 1
            human_cell = (
                f"{h.get('contradiction_kind') or '—'} / "
                f"{h.get('hard_constraint') or '—'}"
                if h.get("verdict") == "contradicted"
                else f"{h.get('verdict')}（不是矛盾）"
            )
            cells = []
            for n, j in enumerate(judged):
                judgment = j.get(item_id)
                if judgment is None:
                    cells.append(missing[n])
                    continue
                claim = judgment.hard_constraint_claim
                cells.append(
                    f"{judgment.verdict} / {judgment.contradiction_kind or '—'} / "
                    f"主张 {claim.violated_constraint if claim else '—'}"
                )
            lines.append(f"| {item_id} | {human_cell} | " + " | ".join(cells) + " |")
        if not rows:
            lines.append("| （无） | | " + " | ".join("" for _ in judged) + " |")
        lines.append("")

        # 3. Severe defects.
        human_rules = set(_critical_rules(sheet))
        human_h = {
            str(v["hard_constraint"])
            for v in human.values()
            if v.get("hard_constraint")
        }
        lines += [
            "### 3. 严重缺陷",
            "",
            f"- 人工：严重缺陷 {sorted(human_rules) or '无'}；"
            f"违反的 H {sorted(human_h) or '无'}",
        ]
        for n, output in enumerate(outputs, start=1):
            if output is None:
                lines.append(f"- Judge 第 {n} 轮：输出缺失或无效")
                continue
            rules = sorted({c.rule_id for c in output.critical_candidates})
            claims = sorted(
                {
                    j.hard_constraint_claim.violated_constraint
                    for j in _judgments(output).values()
                    if j.hard_constraint_claim is not None
                }
            )
            lines.append(
                f"- Judge 第 {n} 轮：候选 {rules or '无'}；硬约束主张 {claims or '无'}"
                f"（与人工相同的 H：{sorted(set(claims) & human_h) or '无'}）"
            )
        lines.append("")

        # 4. Evidence quotes.
        lines += ["### 4. 证据引用（逐字核验）", ""]
        human_quotes = [q for v in human.values() for q in v.get("quotes") or []]
        bad_human = [q for q in human_quotes if not index.check(q).valid]
        lines.append(
            f"- 人工：引用 {len(human_quotes)} 段，"
            f"未在文档中找到或过短 {len(bad_human)} 段"
        )
        for n, output in enumerate(outputs, start=1):
            if output is None:
                lines.append(f"- Judge 第 {n} 轮：输出缺失或无效")
                continue
            quotes = [
                (j.item_id, q)
                for j in _judgments(output).values()
                for q in (
                    *j.evidence_quotes,
                    *(
                        j.hard_constraint_claim.quotes
                        if j.hard_constraint_claim
                        else ()
                    ),
                )
            ]
            bad = [(i, q) for i, q in quotes if not index.check(q).valid]
            lines.append(
                f"- Judge 第 {n} 轮：引用 {len(quotes)} 段，无效 {len(bad)} 段"
                + (f"（{', '.join(sorted({i for i, _ in bad}))}）" if bad else "")
            )
        lines.append("")

        # 5. Reasonable alternatives (conflicts and design choices).
        lines += ["### 5. 合理替代方案与冲突取舍", ""]
        conflict_items = sorted({i for k in case.conflicts for i in k.items})
        if not conflict_items:
            lines += ["本用例没有冲突项。", ""]
        for item_id in conflict_items:
            cells = []
            for n, j in enumerate(judged):
                judgment = j.get(item_id)
                if judgment is None:
                    cells.append(missing[n])
                    continue
                penalised = judgment.verdict == "contradicted" or (
                    judgment.hard_constraint_claim is not None
                )
                cells.append(
                    judgment.verdict + ("（把取舍判为违规）" if penalised else "")
                )
            lines.append(
                f"- {item_id}：人工 {human.get(item_id, {}).get('verdict')}；"
                + "；".join(f"第 {n} 轮 {c}" for n, c in enumerate(cells, start=1))
            )
        lines.append("")
    text = "\n".join(lines)
    write_text_once(layout.review / "calibration-comparison.md", text)
    return text
