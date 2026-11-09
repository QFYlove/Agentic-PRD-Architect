from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from prd_benchmark.cases import Case
from prd_benchmark.evidence import EvidenceIndex, impact_problems
from prd_benchmark.human import HumanReview
from prd_benchmark.judge import (
    DIMENSIONS,
    CriticalCandidate,
    Defect,
    DimensionJudgment,
    ItemJudgment,
    JudgeOutput,
    JudgeRequest,
    MockJudge,
    structural_problems,
)
from prd_benchmark.scoring import (
    PassScore,
    aggregate_document,
    basis_problem,
    candidate_id,
    correctness_cap,
    hard_candidate_id,
)

DOCUMENT = (
    "# 采购审批\n\n预估金额大于或等于 2 万元的，主管通过后还需财务审批。\n"
    "48 小时未处理时提醒审批人。\n审批人 72 小时未处理时自动通过。\n"
    "被驳回的申请必须作废，不能修改后重新提交。\n"
    "实际金额超出预估时无需重新审批，按原审批结果下单。"
)
QUOTE = "主管通过后还需财务审批"
AUTO = "审批人 72 小时未处理时自动通过"
H3_CLAIM: dict[str, Any] = {
    "violated_constraint": "H3",
    "quotes": [AUTO],
    "behavior_impact": f"「{AUTO}」会让无人审批的申请直接进入采购，题面要求上报上级",
    "defect_key": "timeout-auto-approve",
}
H6_CLAIM: dict[str, Any] = {
    "violated_constraint": "H6",
    "quotes": ["被驳回的申请必须作废，不能修改后重新提交"],
    "behavior_impact": "「不能修改后重新提交」使申请人无法修改重提，只能新建申请",
    "defect_key": "no-resubmit",
}
C2_GENERAL: dict[str, Any] = {
    "verdict": "contradicted",
    "contradiction_kind": "general",
    "evidence_quotes": ["实际金额超出预估时无需重新审批"],
    "behavior_impact": (
        "「实际金额超出预估时无需重新审批」把待澄清的重审规则写成定论，超额采购绕过财务"
    ),
    "defect_key": "no-reapproval",
    "rule_basis": ["C2"],
}


def _items(case: Case, overrides: dict[str, dict[str, Any]]) -> list[ItemJudgment]:
    ids = [item.id for item in case.required_items]
    ids += [item.id for item in case.clarifications]
    judged = []
    for item_id in ids:
        spec: dict[str, Any] = {
            "item_id": item_id,
            "verdict": "covered",
            "evidence_quotes": [QUOTE],
            "rationale": "test",
        }
        spec.update(overrides.get(item_id, {}))
        if spec["verdict"] == "missing":
            spec["evidence_quotes"] = []
        judged.append(ItemJudgment.model_validate(spec))
    return judged


def _output(case: Case, anchor: int = 4, **overrides: Any) -> JudgeOutput:
    """Every item covered unless overridden: ``_output(case, R3={...})``."""
    judged = _items(case, overrides)
    defects = () if anchor == 4 else (Defect(description="gap"),)
    dims = [
        DimensionJudgment(
            dimension=name, anchor=anchor, evidence_quotes=(QUOTE,), defects=defects
        )
        for name in DIMENSIONS
    ]
    return JudgeOutput(
        judge_id="test",
        items=tuple(j for j in judged if j.item_id.startswith("R")),
        clarifications=tuple(j for j in judged if j.item_id.startswith("C")),
        dimensions=tuple(dims),
    )


def _aggregate(
    case: Case,
    outputs: list[JudgeOutput],
    human: HumanReview | None = None,
    document: str = DOCUMENT,
) -> Any:
    return aggregate_document(
        doc_id="d-1",
        case=case,
        labels=["A"],
        document=document,
        outputs=[(n, out, []) for n, out in enumerate(outputs, start=1)],
        human=human,
        pass_threshold=70,
    )


def _decide(*pairs: tuple[str, str], scope: str = "full", **extra: Any) -> HumanReview:
    return HumanReview.model_validate(
        {
            "doc_id": "d-1",
            "reviewer": "r1",
            "scope": scope,
            "critical_decisions": [
                {"candidate_id": cid, "decision": d} for cid, d in pairs
            ],
            **extra,
        }
    )


H3_ID = hard_candidate_id("H3", "timeout-auto-approve")
H6_ID = hard_candidate_id("H6", "no-resubmit")


# --- evidence and contract --------------------------------------------------


def test_evidence_requires_verbatim_quotes() -> None:
    index = EvidenceIndex("第一行\n  主管通过后\n还需财务审批。")
    assert index.check("主管通过后 还需财务审批").valid  # whitespace may differ
    assert not index.check("主管同意后还需财务审批").valid  # wording may not
    assert index.check("审批").reason == "too_short"


@pytest.mark.parametrize(
    ("impact", "problem"),
    [
        (None, "impact_missing"),
        ("超时会自动通过，导致绕过审批", "impact_without_document_quote"),
        ("「超时后自动批准全部申请」会绕过审批直接下单", "impact_quote_not_found"),
        (f"「{AUTO}」与题面不一致", "impact_too_generic"),
        (f"「{AUTO}」存在矛盾。", "impact_too_generic"),
    ],
)
def test_behavior_impact_must_be_grounded_and_specific(
    impact: str | None, problem: str
) -> None:
    assert problem in impact_problems(impact, EvidenceIndex(DOCUMENT))


def test_specific_grounded_impact_passes() -> None:
    impact = H3_CLAIM["behavior_impact"]
    assert impact_problems(impact, EvidenceIndex(DOCUMENT)) == []


def test_contract_rejects_totals_and_incoherent_judgments() -> None:
    with pytest.raises(ValidationError):
        JudgeOutput.model_validate(
            {"judge_id": "x", "items": [], "dimensions": [], "total_score": 88}
        )
    base: dict[str, Any] = {"item_id": "R1", "evidence_quotes": ["q"], "rationale": "r"}
    with pytest.raises(ValidationError, match="needs evidence"):
        ItemJudgment(item_id="R1", verdict="covered", rationale="r")
    with pytest.raises(ValidationError, match="behavior_impact"):
        ItemJudgment(**base, verdict="contradicted", contradiction_kind="internal")
    with pytest.raises(ValidationError, match="defect_key"):
        ItemJudgment(
            **base, verdict="contradicted", contradiction_kind="internal",
            behavior_impact="x",
        )  # fmt: skip
    with pytest.raises(ValidationError, match="basis"):
        ItemJudgment(
            **base, verdict="contradicted", contradiction_kind="general",
            behavior_impact="x", defect_key="some-defect",
        )  # fmt: skip
    with pytest.raises(ValidationError, match="only contradictions"):
        ItemJudgment(**base, verdict="partial", behavior_impact="x")
    with pytest.raises(ValidationError):  # "hard_constraint" is no longer a kind
        ItemJudgment.model_validate(
            {**base, "verdict": "contradicted", "contradiction_kind": "hard_constraint"}
        )
    with pytest.raises(ValidationError):
        ItemJudgment.model_validate(
            {**base, "verdict": "covered", "defect_key": "Not A Slug"}
        )
    with pytest.raises(ValidationError):
        DimensionJudgment(dimension="flow", anchor=3)  # anchor < 4 needs a defect


def test_structural_problems_catch_missing_items(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    output = _output(case)
    assert structural_problems(output, case) == []
    truncated = output.model_copy(update={"items": output.items[:-1]})
    assert structural_problems(truncated, case)


@pytest.mark.parametrize(
    ("basis", "problem"),
    [
        (("R3",), None),
        (("C1",), None),
        (("H3",), "basis_is_hard_constraint"),
        (("K1",), "basis_is_conflict"),
        (("R99",), "unknown_basis"),
        ((), "rule_basis_missing"),
    ],
)
def test_rule_basis_checks(
    cases: dict[str, Case], basis: tuple[str, ...], problem: str | None
) -> None:
    assert basis_problem(basis, cases["PQB-P03"]) == problem


def test_p07_relation_kinds_as_rule_basis(cases: dict[str, Case]) -> None:
    p07 = cases["PQB-P07"]
    kinds = {r.id: r.kind for r in p07.rule_relations}
    for rid, kind in kinds.items():
        expected = "basis_is_design_choice" if kind == "design_choice" else None
        assert basis_problem((rid,), p07) == expected, rid


# --- caps --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("missing", "general", "hard", "cap"),
    [
        (0, 0, 0, 4),
        (1, 0, 0, 3),
        (2, 0, 0, 2),
        (0, 1, 0, 3),
        (0, 2, 0, 2),
        (1, 1, 0, 3),
        (2, 2, 0, 2),
        (0, 0, 1, 1),
        (3, 3, 1, 1),
    ],
)
def test_correctness_caps_treat_problem_kinds_separately(
    missing: int, general: int, hard: int, cap: int
) -> None:
    assert correctness_cap(missing, general, hard) == cap


def test_full_marks_and_continuous_coverage(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    score = _aggregate(case, [_output(case)])
    assert score.status == "final" and score.final_total == 100
    core = next(i for i in case.required_items if i.core)
    total_weight = sum(i.weight for i in case.required_items)
    overrides: dict[str, Any] = {core.id: {"verdict": "missing"}}
    missing = _aggregate(case, [_output(case, **overrides)])
    assert missing.metric("coverage_ratio") == pytest.approx(
        1 - 2 / total_weight, abs=1e-4
    )


def test_missing_core_clarification_caps_without_candidate(
    cases: dict[str, Case],
) -> None:
    case = cases["PQB-P03"]
    score = _aggregate(case, [_output(case, C1={"verdict": "missing"})])
    assert score.scenarios["final"]["correctness_caps"] == [3]
    assert score.candidates == []


def test_internal_contradiction_goes_to_consistency(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    internal = {
        "verdict": "contradicted",
        "contradiction_kind": "internal",
        "evidence_quotes": [AUTO],
        "behavior_impact": f"「{AUTO}」与上一行的提醒规则不同，超时后的处理无法确定",
        "defect_key": "timeout-inconsistent",
    }
    score = _aggregate(case, [_output(case, R12=internal)])
    assert score.passes[0].counts["internal_contradictions"] == 1
    assert score.scenarios["final"]["correctness_caps"] == [4]
    assert score.scenarios["final"]["general_contradictions"] == [0]
    r12 = next(j for j in score.passes[0].judgments if j.item_id == "R12")
    assert r12.credited_score == 0.5


def test_same_defect_key_counts_once(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    r12 = {**C2_GENERAL, "rule_basis": ["R12"]}
    separate = _aggregate(case, [_output(case, R12=r12, C2=C2_GENERAL)])
    other = {**r12, "defect_key": "partial-delivery"}
    distinct = _aggregate(case, [_output(case, R12=other, C2=C2_GENERAL)])
    assert separate.scenarios["final"]["general_contradictions"] == [1]
    assert separate.scenarios["final"]["correctness_caps"] == [3]
    assert distinct.scenarios["final"]["general_contradictions"] == [2]
    assert distinct.scenarios["final"]["correctness_caps"] == [2]


# --- hard-constraint claims and decisions -------------------------------------


def test_pending_claim_withholds_the_final_score(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    output = _output(case, R8={"verdict": "partial", "hard_constraint_claim": H3_CLAIM})
    score = _aggregate(case, [output])
    assert score.status == "pending"
    assert score.final_total is None
    assert score.provisional_pass is None
    assert set(score.scenarios) == {"base", "if_confirmed", "if_rejected"}
    assert score.total("base") == score.total("if_rejected")
    assert score.total("if_confirmed") < score.total("base")
    assert score.scenarios["if_confirmed"]["correctness_caps"] == [1]
    assert score.scenarios["base"]["correctness_caps"] == [4]
    [candidate] = score.candidates
    assert candidate.candidate_id == H3_ID
    assert (candidate.rule_id, candidate.decision) == ("G1", "pending")
    assert candidate.affects_score


def test_confirm_applies_cap_and_reject_restores_the_item(
    cases: dict[str, Case],
) -> None:
    case = cases["PQB-P03"]
    output = _output(case, R8={"verdict": "partial", "hard_constraint_claim": H3_CLAIM})
    pending = _aggregate(case, [output])
    confirmed = _aggregate(case, [output], _decide((H3_ID, "confirmed")))
    rejected = _aggregate(case, [output], _decide((H3_ID, "rejected")))
    assert confirmed.final_total == pending.total("if_confirmed")
    assert confirmed.scenarios["final"]["correctness_caps"] == [1]
    assert confirmed.provisional_pass is False
    # Rejection removes exactly the claim's penalty: R8 keeps its own partial.
    assert rejected.final_total == pending.total("base")
    assert rejected.scenarios["final"]["correctness_caps"] == [4]
    assert rejected.scenarios["final"]["general_contradictions"] == [0]
    r8 = next(j for j in rejected.passes[0].judgments if j.item_id == "R8")
    assert (r8.verdict, r8.credited_score) == ("partial", 0.5)


def test_independent_general_contradiction_survives_rejection(
    cases: dict[str, Case],
) -> None:
    case = cases["PQB-P03"]
    # C2 shares the H6 claim's defect key but cites its own text and basis.
    independent = {**C2_GENERAL, "defect_key": "no-resubmit"}
    output = _output(
        case,
        R4={"verdict": "partial", "hard_constraint_claim": H6_CLAIM},
        C2=independent,
    )
    rejected = _aggregate(case, [output], _decide((H6_ID, "rejected")))
    assert rejected.scenarios["final"]["general_contradictions"] == [1]
    assert rejected.scenarios["final"]["correctness_caps"] == [3]
    # When confirmed, the shared key is counted once, as the hard violation.
    confirmed = _aggregate(case, [output], _decide((H6_ID, "confirmed")))
    assert confirmed.scenarios["final"]["general_contradictions"] == [0]
    assert confirmed.scenarios["final"]["correctness_caps"] == [1]


def test_general_contradiction_restating_the_claim_does_not_count(
    cases: dict[str, Case],
) -> None:
    case = cases["PQB-P03"]
    dependent = {
        "verdict": "contradicted",
        "contradiction_kind": "general",
        "evidence_quotes": [AUTO],
        "behavior_impact": H3_CLAIM["behavior_impact"],
        "defect_key": "timeout-auto-approve",
        "rule_basis": ["R8"],
        "hard_constraint_claim": H3_CLAIM,
    }
    output = _output(case, R8=dependent)
    rejected = _aggregate(case, [output], _decide((H3_ID, "rejected")))
    r8 = next(j for j in rejected.passes[0].judgments if j.item_id == "R8")
    assert r8.problem == "depends_on_hard_claim" and not r8.verified
    assert rejected.scenarios["final"]["general_contradictions"] == [0]
    assert rejected.scenarios["final"]["correctness_caps"] == [4]


def test_multiple_candidates_are_independent(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    output = _output(
        case,
        R8={"verdict": "partial", "hard_constraint_claim": H3_CLAIM},
        R4={"verdict": "partial", "hard_constraint_claim": H6_CLAIM},
    )
    pending = _aggregate(case, [output])
    assert set(pending.candidate_effects) == {H3_ID, H6_ID}
    one = _aggregate(case, [output], _decide((H3_ID, "confirmed")))
    assert one.status == "pending" and one.final_total is None
    # H3 settled as confirmed; H6 still open: the two scenarios differ only by H6.
    assert one.total("if_rejected") == pending.candidate_effects[H3_ID]
    assert one.total("if_confirmed") == pending.total("if_confirmed")
    both = _aggregate(
        case, [output], _decide((H3_ID, "confirmed"), (H6_ID, "rejected"))
    )
    assert both.status == "final"
    assert both.final_total == one.total("if_rejected")
    decisions = {c.candidate_id: c.decision for c in both.candidates}
    assert decisions == {H3_ID: "confirmed", H6_ID: "rejected"}


def test_claims_in_two_passes_share_one_candidate(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    first = _output(case, R8={"verdict": "partial", "hard_constraint_claim": H3_CLAIM})
    second = _output(case, R8={"verdict": "covered", "hard_constraint_claim": H3_CLAIM})
    score = _aggregate(case, [first, second], _decide((H3_ID, "confirmed")))
    assert [c.candidate_id for c in score.candidates] == [H3_ID]
    assert score.scenarios["final"]["correctness_caps"] == [1, 1]


@pytest.mark.parametrize("ref", ["H99", "L1", "R8", "K1"])
def test_claim_must_cite_an_explicit_h(cases: dict[str, Case], ref: str) -> None:
    case = cases["PQB-P03"]
    claim = {**H3_CLAIM, "violated_constraint": ref}
    score = _aggregate(
        case, [_output(case, R8={"verdict": "partial", "hard_constraint_claim": claim})]
    )
    assert score.candidates == []
    assert score.status == "final"
    [invalid] = score.passes[0].invalid_claims
    assert "not_explicit_hard_constraint" in invalid["reasons"]


def test_claim_with_fabricated_quote_or_impact_is_refused(
    cases: dict[str, Case],
) -> None:
    case = cases["PQB-P03"]
    fake_quote = {**H3_CLAIM, "quotes": ["超时后自动批准全部申请"]}
    fake_impact = {
        **H3_CLAIM,
        "behavior_impact": "「超时后自动批准全部申请」会跳过审批直接下单",
    }
    for claim, reason in (
        (fake_quote, "quote_not_found"),
        (fake_impact, "impact_quote_not_found"),
    ):
        score = _aggregate(
            case,
            [_output(case, R8={"verdict": "partial", "hard_constraint_claim": claim})],
        )
        assert score.candidates == []
        assert reason in score.passes[0].invalid_claims[0]["reasons"]


def test_judge_candidate_on_claim_quote_merges(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    base = _output(case, R8={"verdict": "partial", "hard_constraint_claim": H3_CLAIM})
    output = base.model_copy(
        update={
            "critical_candidates": (
                CriticalCandidate(
                    rule_id="P03-X1", quote=AUTO, rationale="超时自动通过"
                ),
            )
        }
    )
    score = _aggregate(case, [output])
    [candidate] = score.candidates
    assert candidate.rule_id == "P03-X1" and candidate.merged_rule_ids == ["G1"]
    confirmed = _aggregate(case, [output], _decide((candidate.aliases[0], "confirmed")))
    assert confirmed.final_total == score.total("if_confirmed")


def test_human_override_claim_counts_as_confirmed(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    human = HumanReview.model_validate(
        {
            "doc_id": "d-1",
            "reviewer": "r1",
            "scope": "full",
            "item_overrides": {
                "R8": {
                    "verdict": "partial",
                    "hard_constraint": "H3",
                    "defect_key": "timeout-auto-approve",
                },
                "R3": {"verdict": "missing"},
            },  # fmt: skip
            "dimension_overrides": {"flow": 2},
        }
    )
    score = _aggregate(case, [_output(case)], human)
    assert score.status == "final"
    assert score.scenarios["final"]["correctness_caps"] == [1]
    assert score.passes[0].judge_anchors["flow"] == 2
    r3 = next(j for j in score.passes[0].judgments if j.item_id == "R3")
    assert (r3.verdict, r3.source) == ("missing", "human")


def test_unknown_decision_ids_are_reported(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    score = _aggregate(case, [_output(case)], _decide(("deadbeef00", "confirmed")))
    assert score.unknown_decisions == ["deadbeef00"]


def test_provenance_follows_review_scope(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    assert _aggregate(case, [_output(case)]).provenance == "auto"
    partial = _aggregate(case, [_output(case)], _decide(scope="partial"))
    assert partial.provenance == "partially_reviewed"


def test_two_passes_are_averaged_and_disagreements_flagged(
    cases: dict[str, Case],
) -> None:
    case = cases["PQB-P03"]
    score = _aggregate(
        case, [_output(case), _output(case, anchor=2, R1={"verdict": "partial"})]
    )
    assert score.disagreements == ["R1"]
    totals = [p.evaluate(frozenset()).total for p in score.passes]
    assert score.final_total == pytest.approx(sum(totals) / 2)


def test_pass_score_is_reproducible(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    output = _output(case, R8={"verdict": "partial", "hard_constraint_claim": H3_CLAIM})
    first = PassScore(1, output, case, DOCUMENT)
    assert first.evaluate(frozenset({H3_ID})) == first.evaluate(frozenset({H3_ID}))


async def test_mock_judge_is_deterministic_and_schema_valid(
    cases: dict[str, Case],
) -> None:
    case = cases["PQB-P05"]
    order = tuple(i.id for i in case.required_items) + tuple(
        c.id for c in case.clarifications
    )
    request = JudgeRequest("d-1", case, DOCUMENT, 1, order)
    first = await MockJudge().evaluate(request)
    assert first == await MockJudge().evaluate(request)
    assert structural_problems(first, case) == []
    index = EvidenceIndex(DOCUMENT)
    for judged in [*first.items, *first.clarifications]:
        assert all(index.check(q).valid for q in judged.evidence_quotes)


# --- pass status is separate from the numeric score --------------------------

SELF = "被驳回的申请必须作废，不能修改后重新提交"


def _with_candidates(output: JudgeOutput, *rules: str) -> JudgeOutput:
    proposed = tuple(
        CriticalCandidate(rule_id=r, quote=SELF, rationale="test") for r in rules
    )
    return output.model_copy(update={"critical_candidates": proposed})


@pytest.mark.parametrize("rule", ["G2", "G3", "G4", "G5", "P03-X2"])
def test_any_pending_candidate_keeps_pass_status_pending(
    cases: dict[str, Case], rule: str
) -> None:
    case = cases["PQB-P03"]
    score = _aggregate(case, [_with_candidates(_output(case), rule)])
    assert score.final_total == 100  # the number is not withheld ...
    assert score.pass_status == "pending"  # ... the outcome is
    assert score.provisional_pass is None
    assert score.status == "pending"


def test_pending_h_claim_keeps_pass_status_pending(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    output = _output(case, R8={"verdict": "partial", "hard_constraint_claim": H3_CLAIM})
    score = _aggregate(case, [output])
    assert score.final_total is None and score.pass_status == "pending"


def test_pass_status_updates_with_each_decision(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    output = _with_candidates(
        _output(case, R8={"verdict": "partial", "hard_constraint_claim": H3_CLAIM}),
        "G3",
    )
    g3 = candidate_id("G3", None, SELF)
    h_only = _aggregate(case, [output], _decide((H3_ID, "rejected")))
    assert h_only.final_total is not None  # H settled: number available
    assert h_only.pass_status == "pending"  # G3 still open
    passed = _aggregate(case, [output], _decide((H3_ID, "rejected"), (g3, "rejected")))
    assert passed.pass_status == "pass" and passed.provisional_pass is True
    failed = _aggregate(case, [output], _decide((H3_ID, "rejected"), (g3, "confirmed")))
    assert failed.pass_status == "fail"
    assert failed.final_total == passed.final_total  # G3 never changes the score
    capped = _aggregate(case, [output], _decide((H3_ID, "confirmed"), (g3, "rejected")))
    assert capped.pass_status == "fail"
    assert capped.final_total < passed.final_total


def test_low_score_without_candidates_fails_on_threshold(
    cases: dict[str, Case],
) -> None:
    case = cases["PQB-P03"]
    score = _aggregate(case, [_output(case, anchor=0)])
    assert score.candidates == [] and score.pass_status == "fail"


def test_g2_g5_are_never_folded_into_a_claim(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    claim = {**H6_CLAIM, "quotes": [SELF]}
    output = _with_candidates(
        _output(case, R4={"verdict": "partial", "hard_constraint_claim": claim}),
        "G3",
        "G1",
    )
    score = _aggregate(case, [output])
    by_rule = {c.rule_id: c for c in score.candidates}
    assert set(by_rule) == {"G1", "G3"}  # judge G1 folded, G3 kept separate
    assert by_rule["G1"].affects_score
    assert "judge_candidate_same_quote" in by_rule["G1"].merge_basis
    assert any(f.startswith("shares_quote_with:") for f in by_rule["G3"].review_flags)


def test_two_case_rules_on_one_claim_are_not_folded(cases: dict[str, Case]) -> None:
    case = cases["PQB-P03"]
    claim = {**H6_CLAIM, "quotes": [SELF]}
    output = _with_candidates(
        _output(case, R4={"verdict": "partial", "hard_constraint_claim": claim}),
        "P03-X1",
        "P03-X2",
    )
    score = _aggregate(case, [output])
    rules = sorted(c.rule_id for c in score.candidates)
    assert rules == ["G1", "P03-X1", "P03-X2"]
    claim_c = next(c for c in score.candidates if c.affects_score)
    assert claim_c.rule_id == "G1" and claim_c.merged_rule_ids == []


def test_reused_defect_key_without_shared_text_is_flagged(
    cases: dict[str, Case],
) -> None:
    case = cases["PQB-P03"]
    first = _output(case, R8={"verdict": "partial", "hard_constraint_claim": H3_CLAIM})
    other = {
        **H3_CLAIM,
        "quotes": ["48 小时未处理时提醒审批人"],
        "behavior_impact": "「48 小时未处理时提醒审批人」之后没有上报，申请会卡住",
    }
    second = _output(case, R8={"verdict": "partial", "hard_constraint_claim": other})
    score = _aggregate(case, [first, second])
    [claim] = [c for c in score.candidates if c.affects_score]
    assert claim.occurrences == ["pass1:R8", "pass2:R8"]
    assert "occurrences_share_no_quote" in claim.review_flags


def test_same_h_shared_quote_different_keys_is_flagged_not_merged(
    cases: dict[str, Case],
) -> None:
    case = cases["PQB-P03"]
    renamed = {**H3_CLAIM, "defect_key": "no-escalation"}
    output = _output(
        case,
        R8={"verdict": "partial", "hard_constraint_claim": H3_CLAIM},
        R12={"verdict": "covered", "hard_constraint_claim": renamed},
    )
    score = _aggregate(case, [output])
    claims = [c for c in score.candidates if c.affects_score]
    assert len(claims) == 2
    assert all(
        any(f.startswith("possible_duplicate_of:") for f in c.review_flags)
        for c in claims
    )
