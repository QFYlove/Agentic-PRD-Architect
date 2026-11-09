"""Descriptive batch report (Markdown + CSV). No significance testing."""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from statistics import mean, median, pstdev
from typing import Any

from prd_benchmark.artifacts import BatchLayout, read_json, read_jsonl, write_text_once
from prd_benchmark.cases import Case
from prd_benchmark.config import PilotConfig
from prd_benchmark.judge import DIMENSIONS, MOCK_JUDGE_ID
from prd_benchmark.scoring import DocumentScore

COMPARISONS: tuple[tuple[str, str, str], ...] = (
    ("B.best", "A", "完整产品策略相对一次性生成（含多轮调用与最佳版本选择）"),
    ("B.best", "B.v1", "同一次运行内的变化（含按内部评分选择版本的效应）"),
    ("B.last", "B.v1", "同一次运行内的变化（不经过版本选择）"),
    ("B.last", "A", "最后版本相对一次性生成"),
    ("A", "B.v1", "同 prompt 两次采样的差异：单对样本，只能作为随机波动的初步参考"),
)
LIMITATIONS = (
    "第一阶段每个用例每个条件只运行 1 次，所有数字都是描述性的，不做显著性判断。",
    "B 相对 A 的差异是完整产品策略的效果，包含更多次调用、修订循环和最佳版本选择，"
    "不代表多 Agent 架构的独立因果贡献。",
    "A − B.v1 每个用例只有一对样本，不能可靠估计随机方差。",
    "`deepseek-flash` 是浮动别名；`response.model` 是服务端自报值，不一定能区分快照。",
    "服务端不支持设置温度和 seed，输出不可复现。",
    "盲评存在残余泄露：B 的文本可能更长、更完整。",
    "未经人工审核的分数（provenance = auto）不是客观真值。",
)


PASS_LABELS = {"pass": "是", "fail": "否", "pending": "待定", "unscored": "未评分"}


def _fmt(value: float | None, digits: int = 1) -> str:
    return "" if value is None else f"{value:.{digits}f}"


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3 or pstdev(xs) == 0 or pstdev(ys) == 0:
        return None
    mx, my = mean(xs), mean(ys)
    cov = mean((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    return cov / (pstdev(xs) * pstdev(ys))


class _BatchData:
    def __init__(self, layout: BatchLayout) -> None:
        self.layout = layout
        self.batch = read_json(layout.runs / "batch.json")
        self.metas: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for case_dir in sorted(p for p in layout.runs.iterdir() if p.is_dir()):
            for condition in ("A", "B"):
                run_dir = case_dir / condition
                if (run_dir / "meta.json").exists():
                    key = (case_dir.name, condition)
                    self.metas[key] = read_json(run_dir / "meta.json")
                    self.calls[key] = read_jsonl(run_dir / "calls.jsonl")

    def all_calls(self, condition: str | None = None) -> list[dict[str, Any]]:
        return [
            call
            for (_, cond), calls in self.calls.items()
            if condition is None or cond == condition
            for call in calls
        ]


def _label_totals(scores: list[DocumentScore]) -> dict[tuple[str, str], DocumentScore]:
    by_label: dict[tuple[str, str], DocumentScore] = {}
    for score in scores:
        for label in score.labels:
            by_label[(score.case_id, label)] = score
    return by_label


def _model_section(data: _BatchData) -> list[str]:
    calls = data.all_calls()
    seen = Counter(c["response_model"] for c in calls if c["response_model"])
    missing = sum(1 for c in calls if c["response_model_missing"])
    configured = data.batch["model"]["model_id"]
    drift = len(seen) > 1
    drift_text = "是，批次内出现多个不同值，不得与其他批次合并" if drift else "否"
    lines = [
        "## 1. 批次与模型",
        "",
        f"- 模式：`{data.batch['mode']}`；commit：`{data.batch['git']['commit']}`；"
        f"工作区未提交路径数：{len(data.batch['git']['dirty_paths'] or [])}",
        f"- 配置哈希：`{data.batch['config_sha256'][:12]}`；用例集："
        f"{data.batch['case_set_version']}（{data.batch['case_set_status']}）",
        f"- 条件顺序种子：{data.batch['condition_order_seed']}；"
        f"服务商更新日志日期：{data.batch['provider_changelog_date'] or '未记录'}",
        f"- 配置模型：`{configured}`（浮动别名）",
        f"- 观测到的 `response.model`：{dict(seen) or '无'}；"
        f"缺失 {missing}/{len(calls)} 次调用",
        f"- model_drift：{drift_text}",
    ]
    if seen and set(seen) == {configured}:
        lines.append("- 服务端只返回了别名本身，未暴露快照标识，无法据此核实快照。")
    matched, compared = request_parity(data)
    lines.append(
        "- A 与 B.v1 首次生成请求的哈希一致（同一 prompt、参数与输入）："
        f"{matched}/{compared}"
    )
    return [*lines, ""]


def _first_generator_sha(calls: list[dict[str, Any]]) -> str | None:
    for call in calls:
        if call["node"] == "generator" and call["version"] == 1:
            return str(call["request_sha256"])
    return None


def request_parity(data: _BatchData) -> tuple[int, int]:
    """How many cases sent A and B.v1 a byte-identical generator request."""
    matched = compared = 0
    for case_id in sorted({case for case, _ in data.calls}):
        a = _first_generator_sha(data.calls.get((case_id, "A"), []))
        b = _first_generator_sha(data.calls.get((case_id, "B"), []))
        if a is not None and b is not None:
            compared += 1
            matched += a == b
    return matched, compared


def _scores_section(scores: list[DocumentScore]) -> list[str]:
    header = (
        "| 用例 | 文档 | doc_id | 状态 | 最终总分 | 基础评分 | 确认 H 违规后 | "
        "否决 H 违规后 | 覆盖率 r | 核心覆盖 | "
        + " | ".join(DIMENSIONS)
        + " | 候选(待定/确认) | 暂定合格 | provenance |"
    )
    lines = [
        "## 2. 各文档得分",
        "",
        "连续分数是主要结果；暂定合格（≥70 且无确认严重缺陷）只作辅助描述，"
        "70 分不是经过验证的通用质量标准。",
        "有待裁定的硬约束候选时不给出最终总分，只列出三个情景："
        "基础评分（不应用任何硬约束候选）、确认全部待定候选后、否决全部待定候选后。"
        "覆盖率与维度列在有最终总分时取最终情景，否则取基础评分。",
        "维度列为该维度得分（满分：correctness 20、flow 20、exceptions 15、"
        "acceptance 15、consistency 5）；覆盖率得分 = 25 × r。",
        "",
        header,
        "|" + "---|" * (header.count("|") - 1),
    ]
    for score in sorted(scores, key=lambda s: (s.case_id, s.labels)):
        shown = "final" if score.final_total is not None else "base"
        points = score.points(shown)
        dims = " | ".join(_fmt(points.get(name)) for name in DIMENSIONS)
        verdict = PASS_LABELS[score.pass_status]
        lines.append(
            f"| {score.case_id} | {', '.join(score.labels)} | {score.doc_id} | "
            f"{score.status} | {_fmt(score.final_total)} | "
            f"{_fmt(score.total('base'))} | {_fmt(score.total('if_confirmed'))} | "
            f"{_fmt(score.total('if_rejected'))} | "
            f"{_fmt(score.metric('coverage_ratio', shown), 2)} | "
            f"{_fmt(score.metric('core_coverage_ratio', shown), 2)} | {dims} | "
            f"{len(score.pending_criticals)}/{len(score.confirmed_criticals)} | "
            f"{verdict} | {score.provenance} |"
        )
    pending = sum(1 for s in scores if s.status == "pending")
    withheld = sum(1 for s in scores if s.scored and s.final_total is None)
    unknown = sorted({d for s in scores for d in s.unknown_decisions})
    lines += [
        "",
        f"待裁定文档：{pending}/{len(scores)}；其中因硬约束候选未裁定而不给出最终"
        f"总分：{withheld}。",
    ]
    if unknown:
        lines.append(f"人工裁定引用了不存在的候选 ID：{', '.join(unknown)}（已忽略）。")
    return [*lines, ""]


def _candidates_section(scores: list[DocumentScore]) -> list[str]:
    """Every severe-defect candidate, its decision, and how it was merged."""
    rows = [
        (s, c) for s in sorted(scores, key=lambda s: s.doc_id) for c in s.candidates
    ]
    lines = [
        "## 2a. 严重缺陷候选",
        "",
        "保留规则 ID 是合并后最终使用的规则；合并依据只有三种：同 H 且同 defect_key、"
        "同规则且同引用（跨轮次）、Judge 候选与主张引用同一段原文。"
        "人工复核提示只提醒，不会自动合并或拆分。",
        "",
    ]
    if not rows:
        return [*lines, "无候选。", ""]
    lines += [
        "| doc_id | 候选 ID | 保留规则 ID | 违反 H | defect_key | 状态 | "
        "影响分数 | 出现位置 | 被合并的规则 ID | 合并依据 | 人工复核提示 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for score, c in rows:
        lines.append(
            f"| {score.doc_id} | {c.candidate_id} | {c.rule_id} | "
            f"{c.violated_constraint or ''} | {c.defect_key or ''} | {c.decision} | "
            f"{'是' if c.affects_score else '否'} | {', '.join(c.occurrences)} | "
            f"{', '.join(c.merged_rule_ids)} | {', '.join(c.merge_basis)} | "
            f"{'; '.join(c.review_flags)} |"
        )
    return [*lines, ""]


def _comparison_section(scores: list[DocumentScore], tie_band: float) -> list[str]:
    by_label = _label_totals(scores)
    case_ids = sorted({score.case_id for score in scores})
    lines = ["## 3. 配对比较（描述性）", ""]
    for left, right, meaning in COMPARISONS:
        deltas: list[float] = []
        rows: list[str] = []
        for case_id in case_ids:
            a, b = by_label.get((case_id, left)), by_label.get((case_id, right))
            ta = a.final_total if a else None
            tb = b.final_total if b else None
            if ta is None or tb is None:
                reason = "待裁定或缺少文档" if a and b else "缺少文档或分数"
                rows.append(f"| {case_id} | | | {reason} |")
                continue
            delta = ta - tb
            deltas.append(delta)
            rows.append(f"| {case_id} | {_fmt(ta)} | {_fmt(tb)} | {delta:+.1f} |")
        lines += [
            f"### {left} − {right}",
            "",
            meaning,
            "",
            f"| 用例 | {left} | {right} | 差值 |",
            "|---|---|---|---|",
            *rows,
            "",
        ]
        if deltas:
            better = sum(1 for d in deltas if d >= tie_band)
            worse = sum(1 for d in deltas if d <= -tie_band)
            lines.append(
                f"n={len(deltas)}；差值中位数 {median(deltas):+.1f}，范围 "
                f"{min(deltas):+.1f} 至 {max(deltas):+.1f}；方向：{left} 高 {better}、"
                f"持平 {len(deltas) - better - worse}、{right} 高 {worse}"
                f"（|差值| < {tie_band:g} 记为持平，不代表统计等价）。"
            )
            lines.append("")
    return lines


def _category_section(scores: list[DocumentScore], cases: dict[str, Case]) -> list[str]:
    by_label = _label_totals(scores)
    labels = ("A", "B.best", "B.last", "B.v1")
    lines = [
        "## 4. 按需求类型",
        "",
        "| 类型 | 用例 | " + " | ".join(labels) + " |",
        "|---|---|" + "---|" * len(labels),
    ]
    for case_id in sorted({s.case_id for s in scores}):
        cells = []
        for label in labels:
            score = by_label.get((case_id, label))
            cells.append(_fmt(score.final_total) if score else "")
        lines.append(
            f"| {cases[case_id].category} | {case_id} | " + " | ".join(cells) + " |"
        )
    return [*lines, ""]


def _sum(calls: list[dict[str, Any]], key: str) -> int | None:
    values = [c[key] for c in calls if c.get(key) is not None]
    return sum(values) if values else None


def _cost_section(data: _BatchData, config: PilotConfig) -> list[str]:
    lines = [
        "## 5. Token、耗时与成本",
        "",
        "Token 为逐次调用求和，包含失败尝试与修复调用。"
        "缓存命中 Token 仅在服务端返回时记录。",
        "",
        "| 条件 | 运行数 | 调用数 | 输入 Token | 输出 Token | 缓存命中 Token | "
        "端到端耗时合计(s) | 首 token 延迟中位数(s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    totals: dict[str, dict[str, float | None]] = {}
    for condition in ("A", "B"):
        calls = data.all_calls(condition)
        metas = [m for (_, c), m in data.metas.items() if c == condition]
        walls = [
            float(m["wall_seconds"]) for m in metas if m.get("wall_seconds") is not None
        ]
        firsts = [
            c["first_token_seconds"]
            for c in calls
            if c.get("first_token_seconds") is not None
        ]
        row = {
            "input": _sum(calls, "input_tokens"),
            "output": _sum(calls, "output_tokens"),
            "wall": round(sum(walls), 2) if walls else None,
            "calls": float(len(calls)),
        }
        totals[condition] = {
            k: (float(v) if v is not None else None) for k, v in row.items()
        }
        lines.append(
            f"| {condition} | {len(metas)} | {len(calls)} | {row['input'] or ''} | "
            f"{row['output'] or ''} | {_sum(calls, 'cache_hit_tokens') or ''} | "
            f"{_fmt(row['wall'], 2)} | {_fmt(median(firsts) if firsts else None, 2)} |"
        )
    lines.append("")
    ratios = []
    for key, name in (
        ("calls", "调用数"),
        ("input", "输入 Token"),
        ("output", "输出 Token"),
        ("wall", "耗时"),
    ):
        a, b = totals["A"].get(key), totals["B"].get(key)
        if a and b is not None:
            ratios.append(f"{name} B/A = {b / a:.1f}×")
    if ratios:
        lines += ["倍数：" + "；".join(ratios) + "。", ""]
    budget = data.batch.get("budget")
    if budget:
        lines.append(
            "估算成本（按价目表快照，非账单）："
            f"合计 US${budget['charged_usd_estimate']:.4f}；"
            f"Token 计入 {budget['charged_tokens']}（上限 {budget['token_limit']}，"
            f"费用上限 {budget['usd_limit']}）。"
        )
        for channel, values in sorted(budget.get("by_channel", {}).items()):
            lines.append(
                f"- {channel}：US${values['usd']:.4f}，其中用量未知按最坏情况计入 "
                f"US${values.get('held_unknown_usd', 0.0):.4f}"
            )
        lines.append("")
    lines += ["可核实成本须以账单对账为准；以上均为估算。", ""]
    del config
    return lines


def _reliability_section(data: _BatchData) -> list[str]:
    lines = ["## 6. 可靠性", ""]
    for condition in ("A", "B"):
        metas = [m for (_, c), m in data.metas.items() if c == condition]
        statuses = Counter(str(m.get("status")) for m in metas)
        codes = Counter(str(m.get("error_code")) for m in metas if m.get("error_code"))
        calls = data.all_calls(condition)
        retries = Counter(c["node"] for c in calls if c["attempt"] > 1)
        repairs = sum(1 for c in calls if c["node"] == "repair")
        outcomes = Counter(c["outcome"] for c in calls if c["outcome"] != "ok")
        lines.append(
            f"- {condition}：最终状态 {dict(statuses)}；错误码 {dict(codes) or '无'}；"
            f"重试调用 {dict(retries) or '无'}；修复调用 {repairs}；"
            f"非 ok 调用 {dict(outcomes) or '无'}"
        )
        if condition == "B" and metas:
            passed = sum(1 for m in metas if m.get("quality_gate_passed"))
            lines.append(f"- B 质量门槛通过率：{passed}/{len(metas)}")
    return [*lines, ""]


def _internal_section(data: _BatchData, scores: list[DocumentScore]) -> list[str]:
    by_label = _label_totals(scores)
    lines = [
        "## 7. B 内部评分与外部评分",
        "",
        "| 用例 | 内部 best_score | 外部 B.best 总分 |",
        "|---|---|---|",
    ]
    for (case_id, condition), meta in sorted(data.metas.items()):
        if condition != "B":
            continue
        score = by_label.get((case_id, "B.best"))
        lines.append(
            f"| {case_id} | {_fmt(meta.get('best_score'))} | "
            f"{_fmt(score.final_total if score else None)} |"
        )
    return [*lines, "", "样本量很小，只列出数值，不计算相关系数。", ""]


def _length_section(
    scores: list[DocumentScore], checks: dict[str, dict[str, Any]]
) -> list[str]:
    pairs = [
        (float(checks[s.doc_id]["characters"]), total)
        for s in scores
        if (total := s.final_total) is not None and s.doc_id in checks
    ]
    r = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
    lines = ["## 8. 长度与分数", ""]
    lines.append(
        f"总分与字符数的 Pearson 相关（n={len(pairs)}，仅描述）："
        f"{_fmt(r, 2) if r is not None else '样本不足或无方差'}"
    )
    if len(pairs) >= 3:
        ordered = sorted(pairs)
        third = max(1, len(ordered) // 3)
        tiers = [
            ordered[:third],
            ordered[third : len(ordered) - third],
            ordered[len(ordered) - third :],
        ]
        means = [_fmt(mean(t[1] for t in tier)) if tier else "" for tier in tiers]
        lines.append(f"按长度三分位的平均总分（短/中/长）：{' / '.join(means)}")
    return [*lines, ""]


def _judge_section(scores: list[DocumentScore], judge_ids: set[str]) -> list[str]:
    compared = [s for s in scores if len(s.passes) > 1]
    items = sum(len(s.passes[0].judgments) for s in compared)
    disagreements = sum(len(s.disagreements) for s in compared)
    invalid = sum(len(s.invalid_passes) for s in scores)
    unverified = sum(p.counts["unverified_judgments"] for s in scores for p in s.passes)
    invalid_claims = sum(p.counts["invalid_claims"] for s in scores for p in s.passes)
    agreement = 100 * (1 - disagreements / items) if items else None
    lines = [
        "## 9. Judge 一致性与证据",
        "",
        f"- Judge：{', '.join(sorted(judge_ids)) or '无'}",
        f"- 两次评分的条目一致率：{_fmt(agreement)}%"
        f"（{disagreements} 个不一致条目，已转人工）",
        f"- 作废的 Judge 输出：{invalid}；未核实的判定：{unverified}；"
        f"被拒绝的硬约束主张：{invalid_claims}",
        "- Judge 与人工的一致率：需在人工复核完成后计算。",
    ]
    return [*lines, ""]


def _manual_judge_section(layout: BatchLayout) -> list[str]:
    folder = layout.scores / "judge_raw"
    records = [read_json(p) for p in sorted(folder.glob("*.json")) if folder.exists()]
    manual = [r for r in records if r.get("runner") == "manual-ide-claude-code"]
    if not manual:
        return []
    unknown = Counter(f for r in manual for f in r.get("unknown_fields", []))
    models = Counter(r["session"]["model_identifier"] for r in manual)
    invalid = sum(1 for r in manual if not r.get("valid"))
    lines = [
        "## 9a. 人工 IDE Judge 元数据",
        "",
        f"- 导入次数：{len(manual)}；无效输出：{invalid}",
        f"- 可见的模型标识：{dict(models)}（自报，无法核实快照）",
        "- 成本：未知。人工会话不经过本框架的预算预留，不计入 Token 或费用上限。",
        "- 各字段为 unknown 的次数："
        + ("；".join(f"{k} {v}" for k, v in sorted(unknown.items())) or "无"),
    ]
    return [*lines, ""]


def build_report(
    layout: BatchLayout,
    cases: dict[str, Case],
    scores: list[DocumentScore],
    checks: dict[str, dict[str, Any]],
    config: PilotConfig,
    judge_ids: set[str],
) -> tuple[str, str]:
    data = _BatchData(layout)
    warnings = []
    if data.batch["mode"] == "fake":
        warnings.append(
            "> **模拟运行：** 模型输出来自进程内的模拟服务，不代表任何质量结论。"
        )
    if MOCK_JUDGE_ID in judge_ids:
        warnings.append(
            "> **Mock Judge：** 判定由哈希生成，分数没有任何意义，仅用于验证流程。"
        )
    purpose = data.batch.get("purpose")
    if purpose == "smoke":
        warnings.append(
            "> **技术冒烟测试：** 只验证端到端运行、费用控制、日志和裁定链路，"
            "不是质量结论，不得用于推断 Judge 准确率或多 Agent 效果。"
        )
    if any(j.startswith("manual-ide:") for j in judge_ids):
        warnings.append(
            "> **人工触发的 IDE Judge：** 评审在独立的 Claude Code 会话中由人工执行后"
            "导入；成本未知，未计入预算上限；元数据中未知的字段如实记为 unknown。"
        )
    if any(s.provenance == "auto" for s in scores):
        warnings.append("> 含未经人工审核的分数（provenance = auto），不是客观真值。")
    sections = [
        f"# PRD Quality Benchmark 报告：{layout.batch_id}",
        "",
        *warnings,
        "",
        *_model_section(data),
        *_scores_section(scores),
        *_candidates_section(scores),
        *_comparison_section(scores, config.scoring.tie_band_points),
        *_category_section(scores, cases),
        *_cost_section(data, config),
        *_reliability_section(data),
        *_internal_section(data, scores),
        *_length_section(scores, checks),
        *_judge_section(scores, judge_ids),
        *_manual_judge_section(layout),
        "## 10. 局限性",
        "",
        *[f"- {item}" for item in LIMITATIONS],
        "",
    ]
    return "\n".join(sections), _csv(layout, cases, scores, checks)


def _csv(
    layout: BatchLayout,
    cases: dict[str, Case],
    scores: list[DocumentScore],
    checks: dict[str, dict[str, Any]],
) -> str:
    columns = [
        "batch_id", "case_id", "category", "label", "doc_id", "provenance",
        "status", "final_total", "base_total", "total_if_confirmed",
        "total_if_rejected",
        "coverage_ratio", "core_coverage_ratio", "coverage_points",
        *[f"{name}_points" for name in DIMENSIONS],
        "pending_criticals", "confirmed_criticals", "pass_status", "characters",
    ]  # fmt: skip
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    rows: list[dict[str, Any]] = []
    for score in scores:
        shown = "final" if score.final_total is not None else "base"
        points = score.points(shown)
        for label in score.labels:
            row = {
                "batch_id": layout.batch_id,
                "case_id": score.case_id,
                "category": cases[score.case_id].category,
                "label": label,
                "doc_id": score.doc_id,
                "provenance": score.provenance,
                "status": score.status,
                "final_total": score.final_total,
                "base_total": score.total("base"),
                "total_if_confirmed": score.total("if_confirmed"),
                "total_if_rejected": score.total("if_rejected"),
                "coverage_ratio": score.metric("coverage_ratio", shown),
                "core_coverage_ratio": score.metric("core_coverage_ratio", shown),
                "coverage_points": points.get("coverage"),
                **{f"{n}_points": points.get(n) for n in DIMENSIONS},
                "pending_criticals": len(score.pending_criticals),
                "confirmed_criticals": len(score.confirmed_criticals),
                "pass_status": score.pass_status,
                "characters": checks.get(score.doc_id, {}).get("characters"),
            }
            rows.append({k: ("" if v is None else v) for k, v in row.items()})
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["case_id"]].append(row)
    for case_id in sorted(groups):
        writer.writerows(sorted(groups[case_id], key=lambda r: r["label"]))
    return buffer.getvalue()


def write_report(
    layout: BatchLayout,
    cases: dict[str, Case],
    scores: list[DocumentScore],
    checks: dict[str, dict[str, Any]],
    config: PilotConfig,
    judge_ids: set[str],
    *,
    suffix: str = "",
) -> tuple[str, str]:
    """Write ``<batch><suffix>.md`` and ``.csv``; never overwrites."""
    markdown, table = build_report(layout, cases, scores, checks, config, judge_ids)
    md_path = layout.reports / f"{layout.batch_id}{suffix}.md"
    csv_path = layout.reports / f"{layout.batch_id}{suffix}.csv"
    write_text_once(md_path, markdown)
    write_text_once(csv_path, table)
    return str(md_path), str(csv_path)
