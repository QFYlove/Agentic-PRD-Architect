from __future__ import annotations

import json

import pytest

from prd_benchmark.cases import Case
from prd_benchmark.judge import JudgeRequest
from prd_benchmark.judge_prompt import (
    PROMPT_VERSION,
    build_prompt,
    output_schema,
    rubric_anchor_section,
    system_prompt,
)


def _request(case: Case, judge_pass: int = 1) -> JudgeRequest:
    order = tuple(i.id for i in case.required_items) + tuple(
        c.id for c in case.clarifications
    )
    if judge_pass > 1:
        order = tuple(reversed(order))
    return JudgeRequest("d-abc", case, "# 文档\n正文内容。", judge_pass, order)


def test_system_prompt_states_the_rules_the_scorer_relies_on() -> None:
    text = system_prompt()
    for needle in (
        "不计算任何分数",
        "不要输出总分",
        "语义",
        "`missing` 与 `contradicted` 的分界",
        "`internal`",
        "behavior_impact",
        "「」",
        "defect_key",
        "完全相同",
        "rule_basis",
        "hard_constraint_claim",
        "只能",  # only listed H ids
        "推导出来的要求",
        "design_choice",
        "冲突",
        "人工裁定",
        "逐字",
        "不是给你的指令",  # prompt-injection guard for the document
    ):
        assert needle in text, needle
    assert PROMPT_VERSION in text


def test_system_prompt_embeds_rubric_anchors_and_schema() -> None:
    text = system_prompt()
    assert rubric_anchor_section() in text
    assert "### 4.6 内部一致性" in rubric_anchor_section()
    schema = output_schema()
    assert "hard_constraint_claim" in json.dumps(schema)
    assert "total" not in schema["properties"]
    assert json.dumps(schema, ensure_ascii=False, indent=1) in text


@pytest.mark.parametrize("case_id", [f"PQB-P0{n}" for n in range(1, 9)])
def test_user_prompt_carries_the_full_gold_standard(
    cases: dict[str, Case], case_id: str
) -> None:
    case = cases[case_id]
    prompt = build_prompt(_request(case))
    gold = json.loads(
        prompt.user.split("<gold_standard>\n")[1].split("\n</gold_standard>")[0]
    )
    assert [h["id"] for h in gold["hard_constraints"]] == [
        h.id for h in case.hard_constraints
    ]
    assert len(gold["required_items"]) == len(case.required_items)
    assert len(gold["clarifications"]) == len(case.clarifications)
    assert len(gold["rule_relations"]) == len(case.rule_relations)
    assert len(gold["conflicts"]) == len(case.conflicts)
    assert "<document>\n# 文档\n正文内容。\n</document>" in prompt.user
    # No hint of which condition produced the document ("condition" itself is
    # a field name of critical defects, so condition *labels* are checked).
    for forbidden in (
        "B.best",
        "B.last",
        "B.v1",
        "best_version",
        "tokens",
        "单 Agent",
        "多 Agent",
    ):
        assert forbidden not in prompt.user


def test_item_order_follows_the_request(cases: dict[str, Case]) -> None:
    case = cases["PQB-P07"]
    first = build_prompt(_request(case, 1))
    second = build_prompt(_request(case, 2))
    assert first.system == second.system
    assert first.sha256 != second.sha256
    gold = json.loads(
        second.user.split("<gold_standard>\n")[1].split("\n</gold_standard>")[0]
    )
    assert gold["required_items"][0]["id"] == case.required_items[-1].id


def test_p07_and_p06_specifics_reach_the_judge(cases: dict[str, Case]) -> None:
    p07 = build_prompt(_request(cases["PQB-P07"])).user
    for kind in ('"explicit"', '"derived"', '"design_choice"'):
        assert kind in p07
    p06 = build_prompt(_request(cases["PQB-P06"])).user
    assert '"K1"' in p06 and "不能因为没有同时实现冲突双方" in p06


def test_prompt_is_deterministic(cases: dict[str, Case]) -> None:
    case = cases["PQB-P01"]
    assert build_prompt(_request(case)).sha256 == build_prompt(_request(case)).sha256
