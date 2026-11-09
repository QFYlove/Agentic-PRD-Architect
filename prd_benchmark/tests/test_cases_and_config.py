from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.language import detect_output_language
from prd_benchmark.cases import (
    DEFAULT_CASES_DIR,
    Case,
    freeze_problems,
    load_case,
    load_manifest,
    normalize_whitespace,
)
from prd_benchmark.config import PilotConfig, real_run_blockers


def test_all_eight_cases_load_and_fit_the_product_api(
    cases: dict[str, Case],
) -> None:
    assert sorted(cases) == [f"PQB-P0{n}" for n in range(1, 9)]
    for case in cases.values():
        request = case.frozen_input.to_request()
        language = detect_output_language(
            request.user_idea, request.target_audience, request.user_constraints
        )
        assert language == "zh", case.id
        assert case.case_version == "v0.3", case.id


def test_every_hard_constraint_quotes_the_frozen_input(
    cases: dict[str, Case],
) -> None:
    # Loading already enforces this; assert it explicitly as an audit check.
    for case in cases.values():
        source = case.frozen_input.normalized_text()
        for h in case.hard_constraints:
            assert normalize_whitespace(h.quote) in source, f"{case.id} {h.id}"


def test_hard_constraints_that_must_not_exist(cases: dict[str, Case]) -> None:
    def h_text(case_id: str) -> str:
        return " ".join(h.text + h.quote for h in cases[case_id].hard_constraints)

    p04 = h_text("PQB-P04")
    assert "明显" not in p04 and "仅在" not in p04
    assert "须填写原因" not in h_text("PQB-P03")
    p07 = cases["PQB-P07"]
    assert not any("用人经理" in h.text for h in p07.hard_constraints)
    assert not any(
        "基线" in h.text or "32%" in h.text for h in cases["PQB-P08"].hard_constraints
    )
    p06 = h_text("PQB-P06")
    assert "名额固定" not in p06 and "递补" not in p06 and "超卖" not in p06
    assert "7 天内" in p06
    p01_h3 = next(h for h in cases["PQB-P01"].hard_constraints if h.id == "H3")
    assert p01_h3.text == p01_h3.quote


def test_case_with_unquoted_hard_constraint_is_rejected(tmp_path: Path) -> None:
    source = DEFAULT_CASES_DIR / "PQB-P01-article-favorites.yaml"
    text = source.read_text(encoding="utf-8").replace(
        "quote: 每个用户最多 5000 条收藏", "quote: 每个用户最多 9999 条收藏"
    )
    target = tmp_path / "case.yaml"
    target.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError, match="quote not found"):
        load_case(target)


def test_previously_explicit_rules_are_covered_by_required_items(
    cases: dict[str, Case],
) -> None:
    def item(case_id: str, item_id: str) -> str:
        found = next(i for i in cases[case_id].required_items if i.id == item_id)
        return found.text + found.check

    assert "倒序" in item("PQB-P01", "R5")
    assert "全部审批通过后" in item("PQB-P03", "R5")
    assert "主管" in item("PQB-P03", "R3") and "顺序" in item("PQB-P03", "R3")
    assert "生效" in item("PQB-P04", "R13")
    assert "3 步" in item("PQB-P08", "R9")
    assert "基线" in item("PQB-P08", "R3")


def test_p06_conflicts_are_explicit_and_not_hard_constraints(
    cases: dict[str, Case],
) -> None:
    p06 = cases["PQB-P06"]
    assert [k.id for k in p06.conflicts] == ["K1", "K2", "K3", "K4"]
    assert "首次豁免" in p06.judge_notes and "备选方案" in p06.judge_notes
    h2 = next(h for h in p06.hard_constraints if h.id == "H2")
    assert h2.note and "待业务批准" in h2.note
    assert "不能因为没有同时实现冲突双方" in p06.judge_notes


def test_only_p07_is_frozen(cases: dict[str, Case]) -> None:
    manifest = load_manifest()
    assert manifest.status == "draft"
    for entry in manifest.cases:
        if entry.id == "PQB-P07":
            assert entry.status == "frozen" and entry.sha256
        else:
            assert entry.status == "draft" and entry.sha256 is None
    assert {c.id for c in cases.values() if c.status == "frozen"} == {"PQB-P07"}
    assert freeze_problems(), "draft cases must block a full-set real run"
    assert freeze_problems(case_ids=["PQB-P01"]) == ["PQB-P01 is draft"]


def test_every_core_item_states_its_impact(cases: dict[str, Case]) -> None:
    for case in cases.values():
        core = [(i.id, i.impact) for i in case.required_items if i.core]
        core += [(c.id, c.impact) for c in case.clarifications if c.core]
        for item_id, impact in core:
            assert impact, f"{case.id} {item_id}"


def test_p07_rule_relations_are_classified_and_sourced(
    cases: dict[str, Case],
) -> None:
    p07 = cases["PQB-P07"]
    assert sum(item.core for item in p07.required_items) == 5
    assert "法务" in (p07.frozen_input.target_audience or "")
    relations = {r.id: r for r in p07.rule_relations}
    kinds = {r.kind for r in relations.values()}
    assert kinds == {"explicit", "derived", "design_choice"}
    for relation in relations.values():
        assert relation.reasoning
        if relation.kind != "design_choice":
            assert relation.source_quotes, relation.id
        else:
            assert relation.alternatives, relation.id
        if relation.kind != "explicit":
            assert not relation.constraints, relation.id  # derived never cites H
    text = " ".join(r.text + r.reasoning for r in relations.values())
    assert "最长 2 年" not in text
    # Open questions the reviewer required to stay open.
    questions = " ".join(c.question for c in p07.clarifications)
    for needle in ("撤回或到期后", "阻止匿名化", "超过 3 年", "员工系统", "续期"):
        assert needle in questions, needle
    choices = " ".join(r.text for r in relations.values() if r.kind == "design_choice")
    for needle in ("撤回或到期后", "阻止匿名化", "超过 3 年", "已录用者"):
        assert needle in choices, needle
    h4 = next(h for h in p07.hard_constraints if h.id == "H4")
    assert h4.note and "其他处理不受 H4 限制" in h4.note


def test_p05_r8_accepts_any_reliable_dedup_approach(cases: dict[str, Case]) -> None:
    r8 = next(i for i in cases["PQB-P05"].required_items if i.id == "R8")
    assert "任一" in r8.check
    assert "幂等" in r8.check and "转人工" in r8.check
    c2 = next(c for c in cases["PQB-P05"].clarifications if c.id == "C2")
    assert not c2.core


@pytest.mark.parametrize(
    ("case_id", "clarification_id", "needle"),
    [
        ("PQB-P04", "C1", "恰好"),
        ("PQB-P04", "C2", "约定取货时间"),
        ("PQB-P06", "C1", "拍板"),
        ("PQB-P08", "C1", "观察期"),
        ("PQB-P08", "C2", "最小可检测效应"),
    ],
)
def test_listed_ambiguities_remain_clarifications(
    cases: dict[str, Case], case_id: str, clarification_id: str, needle: str
) -> None:
    item = next(c for c in cases[case_id].clarifications if c.id == clarification_id)
    assert needle in item.question


def test_ambiguities_are_not_encoded_as_hard_constraints(
    cases: dict[str, Case],
) -> None:
    p04 = {h.id: h for h in cases["PQB-P04"].hard_constraints}
    assert p04["H2"].note and "C1" in p04["H2"].note and "C2" in p04["H2"].note
    assert p04["H6"].note and "C6" in p04["H6"].note
    p08 = {h.id: h for h in cases["PQB-P08"].hard_constraints}
    assert p08["H4"].note and "任一解读都不违反" in p08["H4"].note


def test_real_runs_are_blocked_by_the_pilot_config(config: PilotConfig) -> None:
    assert config.approvals.real_model_calls == "not_approved"
    assert config.approvals.judge_calls == "not_approved"
    assert config.approvals.other_keyed_calls == "not_approved"
    blockers = real_run_blockers(
        config,
        confirm_spend=True,
        case_freeze_problems=freeze_problems(),
        provider_changelog_date="2026-10-17",
    )
    assert "approvals.real_model_calls is not 'approved'" in blockers


def test_pilot_model_and_condition_b_defaults(config: PilotConfig) -> None:
    assert config.model.model_id == "deepseek-flash"
    assert config.model.model_id_is_floating_alias
    assert config.model.record_response_model == "required"
    b = config.conditions.B
    assert (b.quality_threshold, b.max_iterations, b.timeouts_seconds.run) == (
        85,
        3,
        600,
    )
    assert b.wait_for_completion_seconds > b.timeouts_seconds.run
    assert b.primary_result == "best_version"


def test_freeze_detects_hash_mismatch(tmp_path: Path) -> None:
    for source in (p for p in DEFAULT_CASES_DIR.iterdir() if p.is_file()):
        (tmp_path / source.name).write_bytes(source.read_bytes())
    manifest = (tmp_path / "manifest.yaml").read_text(encoding="utf-8")
    manifest = manifest.replace("sha256: null", f'sha256: "{"0" * 64}"', 1)
    assert "sha256: null" in manifest  # P01 now carries the wrong hash
    (tmp_path / "manifest.yaml").write_text(manifest, encoding="utf-8")
    problems = freeze_problems(tmp_path)
    assert any("sha256 does not match" in p for p in problems)
