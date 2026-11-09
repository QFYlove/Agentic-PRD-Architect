"""V2 review, scoring, plan and PRD-quality tests (PA-002, PA-003, PA-006, PA-008)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.prd_quality import check_prd, outline, sections_matching
from backend.rubric import ROLE_RUBRICS, RUBRIC_VERSION, rubric_document
from backend.schemas import (
    ChangeType,
    DeclinedFinding,
    DimensionScoreInput,
    FeedbackItem,
    FeedbackSeverity,
    FindingCategory,
    FindingStatus,
    GateStatus,
    OptimizerOutput,
    ResolutionInput,
    ReviewerOutput,
    ReviewRole,
    RevisionItemInput,
    RevisionPriority,
    RevisionSource,
    RoleReview,
)
from backend.scoring import (
    MAX_FINDINGS_PER_ROLE,
    build_evaluation,
    build_revision_plan,
    deduplicate,
    evaluate_gate,
    normalize_review,
    overall_score,
    role_score,
)
from backend.tests.helpers import finding, review_value, role_review

# --- Rubric and scores ------------------------------------------------------


def test_every_role_rubric_sums_to_one_and_matches_the_spec() -> None:
    weights = {
        role: [round(d.weight * 100) for d in dims]
        for role, dims in ROLE_RUBRICS.items()
    }
    assert weights == {
        "tech": [30, 25, 25, 20],
        "ux": [25, 30, 25, 20],
        "biz": [30, 25, 20, 25],
    }
    document = rubric_document()
    assert document["rubric_version"] == RUBRIC_VERSION
    assert "RoleScore" in str(document["formula"])


def test_role_score_is_the_weighted_mean_of_dimensions() -> None:
    scores = [
        DimensionScoreInput(dimension=d.id, score=s, rationale="r")
        for d, s in zip(ROLE_RUBRICS["tech"], (5, 4, 3, 2), strict=True)
    ]
    # (5*.30 + 4*.25 + 3*.25 + 2*.20) / 5 * 100 = 73
    assert role_score("tech", scores) == 73


def test_overall_score_is_the_rounded_mean_of_the_three_roles() -> None:
    assert overall_score(65, 70, 78) == 71.0
    assert overall_score(80, 82, 83) == 81.7


def test_a_reviewer_cannot_skip_a_dimension_or_score_outside_1_to_5() -> None:
    value = review_value(ReviewRole.TECH, score=80)
    value["dimension_scores"] = value["dimension_scores"][:3]
    with pytest.raises(ValidationError):
        ReviewerOutput.model_validate(value)

    value = review_value(ReviewRole.TECH, score=80)
    value["dimension_scores"][0]["score"] = 7
    with pytest.raises(ValidationError):
        ReviewerOutput.model_validate(value)

    value = review_value(ReviewRole.TECH, score=80)
    value["dimension_scores"][0]["dimension"] = "made_up"
    with pytest.raises(ValidationError):
        ReviewerOutput.model_validate(value)


def test_a_dimension_label_is_accepted_in_place_of_its_id() -> None:
    value = review_value(ReviewRole.TECH, score=80)
    value["dimension_scores"][0]["dimension"] = "技术可行性"
    output = ReviewerOutput.model_validate(value)
    assert output.dimension_scores[0].dimension == "feasibility"


def test_a_model_supplied_total_score_is_rejected() -> None:
    value = review_value(ReviewRole.TECH, score=80)
    value["score"] = 100
    with pytest.raises(ValidationError):
        ReviewerOutput.model_validate(value)


def test_the_stored_review_records_weights_and_rubric_version() -> None:
    review = role_review(ReviewRole.UX, score=76)

    assert review.score == 76
    assert review.rubric_version == RUBRIC_VERSION
    assert [d.weight for d in review.dimension_scores] == [
        d.weight for d in ROLE_RUBRICS["ux"]
    ]
    assert not review.is_legacy_scoring


def test_a_legacy_review_without_dimensions_stays_legacy() -> None:
    legacy = RoleReview.model_validate(
        {"role": "tech", "score": 78, "summary": "Old.", "feedback": ["Old text"]}
    )

    assert legacy.is_legacy_scoring
    assert legacy.score == 78
    assert legacy.feedback[0].severity is FeedbackSeverity.SHOULD_FIX
    evaluation, _ = build_evaluation(
        legacy,
        legacy.model_copy(update={"role": ReviewRole.UX}),
        legacy.model_copy(update={"role": ReviewRole.BIZ}),
        quality_threshold=85,
    )
    assert evaluation.rubric_version is None


def test_nice_to_have_is_stored_as_the_optional_tier() -> None:
    assert FeedbackSeverity("nice_to_have") is FeedbackSeverity.OPTIONAL


# --- Review normalisation ---------------------------------------------------


def test_an_empty_review_is_valid_and_keeps_its_score() -> None:
    review = role_review(ReviewRole.BIZ, score=90, findings=[])

    assert review.feedback == []
    assert review.score == 90


def test_findings_without_evidence_are_dropped_and_counted() -> None:
    review = role_review(
        ReviewRole.TECH,
        score=70,
        findings=[
            finding(FeedbackSeverity.SHOULD_FIX, "Has evidence"),
            finding(FeedbackSeverity.MUST_FIX, "No evidence", evidence=""),
        ],
    )

    assert [item.title for item in review.feedback] == ["Has evidence"]
    assert review.filtered_findings == 1


def test_findings_are_capped_most_severe_first_with_stable_ids() -> None:
    findings = [
        finding(FeedbackSeverity.OPTIONAL, f"Polish {index}", section=f"{index}.1")
        for index in range(6)
    ] + [finding(FeedbackSeverity.MUST_FIX, "Blocker", section="9.9")]
    review = role_review(ReviewRole.TECH, score=70, findings=findings, version=2)

    assert len(review.feedback) == MAX_FINDINGS_PER_ROLE
    assert review.feedback[0].title == "Blocker"
    assert review.filtered_findings == 2
    assert [item.finding_id for item in review.feedback] == [
        f"v2-tech-{n}" for n in range(1, 6)
    ]


def test_summary_is_cut_to_two_sentences_and_strengths_to_three() -> None:
    value = review_value(ReviewRole.UX, score=70)
    value["summary"] = "第一句。第二句。第三句。第四句。"
    value["strengths"] = ["a", "b", "c", "d"]
    review = normalize_review(ReviewerOutput.model_validate(value), version=1)

    assert review.summary == "第一句。第二句。"
    assert review.strengths == ["a", "b", "c"]


def test_a_must_fix_that_only_asks_for_a_number_is_downgraded() -> None:
    """Run 9fa59292: three of four blockers asked for figures nobody had."""
    review = role_review(
        ReviewRole.BIZ,
        score=70,
        findings=[
            finding(
                FeedbackSeverity.MUST_FIX,
                "Quota values missing",
                category=FindingCategory.QUANTIFICATION,
            ),
            finding(
                FeedbackSeverity.MUST_FIX,
                "Unsure blocker",
                section="6.1",
                confidence=0.3,
            ),
        ],
    )

    assert {item.severity for item in review.feedback} == {FeedbackSeverity.SHOULD_FIX}
    assert all(
        item.severity_adjusted_from is FeedbackSeverity.MUST_FIX
        for item in review.feedback
    )


def test_only_resolutions_for_known_findings_are_kept() -> None:
    value = review_value(
        ReviewRole.TECH,
        score=80,
        resolutions=[
            ResolutionInput(
                finding_id="v1-tech-1", status=FindingStatus.RESOLVED, note="ok"
            ),
            ResolutionInput(
                finding_id="v1-made-up", status=FindingStatus.RESOLVED, note=""
            ),
        ],
    )
    review = normalize_review(
        ReviewerOutput.model_validate(value),
        version=2,
        previous_finding_ids=["v1-tech-1"],
    )

    assert [item.finding_id for item in review.resolutions] == ["v1-tech-1"]


# --- Aggregation ------------------------------------------------------------


def _item(role: ReviewRole, title: str, section: str, **extra: object) -> FeedbackItem:
    return FeedbackItem(
        severity=extra.pop("severity", FeedbackSeverity.SHOULD_FIX),  # type: ignore[arg-type]
        issue=str(extra.pop("issue", title)),
        recommendation="Fix it.",
        title=title,
        section=section,
        category=extra.pop("category", FindingCategory.MISSING_FLOW),  # type: ignore[arg-type]
        source_role=role,
        source_roles=[role],
        finding_id=f"v1-{role.value}-{title[:3]}",
        evidence="quote",
    )


def test_the_same_problem_from_three_roles_becomes_one_finding() -> None:
    merged = deduplicate(
        [
            _item(ReviewRole.TECH, "任务失败后缺少恢复机制", "5.4 任务"),
            _item(ReviewRole.UX, "任务失败后的恢复机制缺失", "5.4 下载任务"),
            _item(ReviewRole.BIZ, "任务失败缺少恢复机制影响留存", "§5.4"),
        ]
    )

    assert len(merged) == 1
    assert merged[0].source_roles == [ReviewRole.TECH, ReviewRole.UX, ReviewRole.BIZ]
    assert len(merged[0].merged_from) == 2
    assert len(merged[0].observations) == 3


def test_different_problems_in_the_same_section_are_not_merged() -> None:
    merged = deduplicate(
        [
            _item(ReviewRole.TECH, "分享 token 熵不足", "5.9 分享"),
            _item(ReviewRole.UX, "未登录用户保存入口缺失", "5.9 分享"),
        ]
    )
    assert len(merged) == 2


def test_two_findings_of_one_reviewer_are_never_merged() -> None:
    merged = deduplicate(
        [
            _item(ReviewRole.TECH, "删除幂等未定义", "9 一致性"),
            _item(ReviewRole.TECH, "删除幂等键未定义", "9 一致性"),
        ]
    )
    assert len(merged) == 2


def test_dedup_is_stable_and_keeps_the_most_severe_wording() -> None:
    items = [
        _item(ReviewRole.UX, "支付失败状态未定义", "5.1"),
        _item(
            ReviewRole.TECH,
            "支付失败处理未定义",
            "5.1",
            severity=FeedbackSeverity.MUST_FIX,
        ),
    ]
    first = deduplicate(items)
    second = deduplicate(items)

    assert first == second
    assert first[0].severity is FeedbackSeverity.MUST_FIX
    assert first[0].source_role is ReviewRole.TECH


def test_gate_states_cover_pass_revision_block_and_unscored() -> None:
    clean, gate = build_evaluation(
        *(role_review(role, score=90) for role in ReviewRole), quality_threshold=85
    )
    assert gate.status is GateStatus.PASSED and clean.gate_status is GateStatus.PASSED

    low, gate = build_evaluation(
        *(role_review(role, score=60) for role in ReviewRole), quality_threshold=85
    )
    assert gate.status is GateStatus.NEEDS_REVISION and not gate.threshold_met

    blocker = role_review(
        ReviewRole.TECH,
        score=95,
        findings=[
            finding(
                FeedbackSeverity.MUST_FIX,
                "违反用户硬约束",
                category=FindingCategory.CONSTRAINT_VIOLATION,
            )
        ],
    )
    blocked, gate = build_evaluation(
        blocker,
        role_review(ReviewRole.UX, score=95),
        role_review(ReviewRole.BIZ, score=95),
        quality_threshold=85,
    )
    assert gate.threshold_met and gate.status is GateStatus.BLOCKED
    assert evaluate_gate(None, 85).status is GateStatus.UNSCORED


def test_overall_score_is_recomputable_from_the_stored_dimensions() -> None:
    evaluation, _ = build_evaluation(
        role_review(ReviewRole.TECH, score=65),
        role_review(ReviewRole.UX, score=70),
        role_review(ReviewRole.BIZ, score=78),
        quality_threshold=85,
    )
    for review in (evaluation.tech, evaluation.ux, evaluation.biz):
        assert role_score(review.role.value, review.dimension_scores) == review.score  # type: ignore[arg-type]
    assert evaluation.overall_score == overall_score(
        evaluation.tech.score, evaluation.ux.score, evaluation.biz.score
    )


def test_previous_findings_resolve_by_the_least_resolved_verdict() -> None:
    previous, _ = build_evaluation(
        role_review(
            ReviewRole.TECH,
            score=70,
            findings=[finding(FeedbackSeverity.MUST_FIX, "A")],
        ),
        role_review(
            ReviewRole.UX,
            score=70,
            findings=[finding(FeedbackSeverity.SHOULD_FIX, "B", section="4.1")],
        ),
        role_review(
            ReviewRole.BIZ,
            score=70,
            findings=[finding(FeedbackSeverity.OPTIONAL, "C", section="7.1")],
        ),
        quality_threshold=85,
    )
    ids = [item.finding_id for item in previous.combined_feedback]
    plan = build_revision_plan(
        OptimizerOutput(
            objective="o",
            declined_findings=[DeclinedFinding(finding_id=ids[2], reason="polish")],
        ),
        iteration=1,
        findings=previous.combined_feedback,
        user_override=None,
    )

    def resolved(role: ReviewRole, verdicts: list[ResolutionInput]) -> RoleReview:
        value = review_value(role, score=85, resolutions=verdicts)
        return normalize_review(
            ReviewerOutput.model_validate(value), version=2, previous_finding_ids=ids
        )

    current, _ = build_evaluation(
        resolved(
            ReviewRole.TECH,
            [
                ResolutionInput(
                    finding_id=ids[0], status=FindingStatus.RESOLVED, note="ok"
                )
            ],
        ),
        resolved(
            ReviewRole.UX,
            [
                ResolutionInput(
                    finding_id=ids[0],
                    status=FindingStatus.PARTIALLY_RESOLVED,
                    note="half",
                )
            ],
        ),
        resolved(ReviewRole.BIZ, []),
        quality_threshold=85,
        previous=previous,
        previous_plan=plan,
    )
    status = {item.finding_id: item.status for item in current.finding_resolutions}

    assert status[ids[0]] is FindingStatus.PARTIALLY_RESOLVED
    assert status[ids[1]] is FindingStatus.NOT_CHECKED
    assert status[ids[2]] is FindingStatus.DECLINED


# --- Revision plans -----------------------------------------------------------


def _findings() -> list[FeedbackItem]:
    evaluation, _ = build_evaluation(
        role_review(
            ReviewRole.TECH,
            score=70,
            findings=[finding(FeedbackSeverity.MUST_FIX, "Blocker")],
        ),
        role_review(
            ReviewRole.UX,
            score=70,
            findings=[finding(FeedbackSeverity.SHOULD_FIX, "Gap", section="4.2")],
        ),
        role_review(ReviewRole.BIZ, score=70),
        quality_threshold=85,
    )
    return evaluation.combined_feedback


def _item_input(
    ids: list[str], change: ChangeType, **extra: object
) -> RevisionItemInput:
    return RevisionItemInput(
        change_type=change,
        source_finding_ids=ids,
        target_sections=extra.pop("targets", ["4.2 流程"]),  # type: ignore[arg-type]
        affected_sections=extra.pop("affected", []),  # type: ignore[arg-type]
        issue="i",
        reason="r",
        required_change="c",
        expected_result="e",
        must_preserve=extra.pop("preserve", []),  # type: ignore[arg-type]
        priority=extra.pop("priority", RevisionPriority.LOW),  # type: ignore[arg-type]
    )


def test_plan_sources_come_from_finding_ids_not_the_model() -> None:
    findings = _findings()
    gap = next(f for f in findings if f.severity is FeedbackSeverity.SHOULD_FIX)
    plan = build_revision_plan(
        OptimizerOutput(
            objective="o",
            items=[
                _item_input([str(gap.finding_id), "invented-id"], ChangeType.UPDATE),
                _item_input([], ChangeType.CONSOLIDATE, targets=["3 范围", "5.5 配额"]),
            ],
        ),
        iteration=1,
        findings=findings,
        user_override=None,
    )

    assert plan.plan_version == "v2"
    assert plan.items[0].source_finding_ids == [gap.finding_id]
    assert plan.items[0].source_roles == [RevisionSource.UX]
    assert plan.items[1].source_roles == [RevisionSource.OPTIMIZER]
    assert plan.items[1].target_sections == ["3 范围", "5.5 配额"]


def test_every_change_type_round_trips_with_affected_sections_and_preserves() -> None:
    findings = _findings()
    gap_id = str(
        next(
            f for f in findings if f.severity is FeedbackSeverity.SHOULD_FIX
        ).finding_id
    )
    plan = build_revision_plan(
        OptimizerOutput(
            objective="o",
            items=[
                _item_input(
                    [gap_id],
                    change,
                    affected=["4.2 流程", "12.1 MVP"],
                    preserve=["取消后清理分片"],
                )
                for change in ChangeType
            ],
        ),
        iteration=1,
        findings=findings,
        user_override=None,
    )

    changes = [item.change_type for item in plan.items if item.change_type]
    assert set(changes) == set(ChangeType)
    first = plan.items[0]
    # The target itself is not repeated as an affected section.
    assert first.affected_sections == ["12.1 MVP"]
    assert first.must_preserve == ["取消后清理分片"]


def test_an_unplanned_and_undeclined_blocker_is_added_back() -> None:
    findings = _findings()
    blocker = next(f for f in findings if f.severity is FeedbackSeverity.MUST_FIX)
    plan = build_revision_plan(
        OptimizerOutput(objective="o", items=[]),
        iteration=1,
        findings=findings,
        user_override=None,
    )

    assert [item.source_finding_ids for item in plan.items] == [[blocker.finding_id]]
    assert plan.items[0].priority is RevisionPriority.HIGH


def test_a_user_override_is_always_planned_at_high_priority() -> None:
    plan = build_revision_plan(
        OptimizerOutput(objective="o", items=[_item_input(["user"], ChangeType.ADD)]),
        iteration=1,
        findings=[],
        user_override="Add reconciliation.",
    )

    assert plan.items[0].source_roles == [RevisionSource.USER]
    assert plan.items[0].priority is RevisionPriority.HIGH


# --- PRD quality checks -----------------------------------------------------

GOOD = """# 云盘 PRD

## 1. 产品概述
- 问题：下载与存储割裂。

## 2. 用户与场景
| 用户 | 场景 |
|---|---|
| 学生 | 离线下载 |

## 3. 功能范围
- P0：远程下载。

## 4. 假设与待确认事项
| 事项 | 类型 |
|---|---|
| 免费容量 10 GB [假设] | 假设 |
"""


def test_a_well_formed_prd_has_no_errors() -> None:
    report = check_prd(GOOD)

    assert report.structure_complete
    assert report.tables == 2
    assert report.list_items == 2
    assert [issue for issue in report.issues if issue.severity == "error"] == []
    assert report.unlabeled_figures == 0


def test_a_missing_required_section_marks_the_structure_incomplete() -> None:
    report = check_prd(GOOD.split("## 4.")[0])

    assert not report.structure_complete
    assert report.missing_sections == ["假设与待确认 / Assumptions & open questions"]


def test_duplicate_section_numbers_and_skipped_levels_are_reported() -> None:
    """v2 of run 9fa59292 had two `### 5.5` headings."""
    content = (
        GOOD + "\n### 5.5 第三方分享\n- a\n\n### 5.5 配额\n- b\n\n##### 深层\n- c\n"
    )
    codes = {issue.code for issue in check_prd(content).issues}

    assert "duplicate_section_number" in codes
    assert "heading_level_skip" in codes


def test_unlabelled_figures_and_invented_sources_are_flagged() -> None:
    content = (
        GOOD
        + "\n## 5. 指标\n- 完成率 ≥70%，来源：内部试点观测值。\n- 月费 30—50 元。\n"
    )
    report = check_prd(content)
    codes = [issue.code for issue in report.issues]

    assert report.unlabeled_figures == 2
    assert "fabricated_source" in codes
    # A figure the user supplied needs no label.
    supplied = check_prd(content, user_text="月费 30—50 元")
    assert supplied.unlabeled_figures == 1


def test_headings_inside_code_fences_are_ignored() -> None:
    content = GOOD + "\n```\n# not a heading\n```\n"
    assert check_prd(content).sections == check_prd(GOOD).sections


def test_outline_and_section_extraction_follow_heading_levels() -> None:
    content = (
        "# T\n\n## 5. 需求\n### 5.5 配额\n- a\n### 5.6 回收站\n- b\n## 6. 其他\n- c\n"
    )

    assert outline(content) == [
        "T",
        "  5. 需求",
        "    5.5 配额",
        "    5.6 回收站",
        "  6. 其他",
    ]
    extracted = sections_matching(content, ["5.5 配额与限制"])
    assert "- a" in extracted and "- b" not in extracted


# --- Workflow wiring ----------------------------------------------------------


async def test_reviewers_and_optimizer_receive_the_v2_context() -> None:
    from typing import Any

    from backend.providers.mock import MockLLMProvider
    from backend.schemas import CreateRunRequest, RunStatus
    from backend.tests.helpers import make_manager

    class Capturing(MockLLMProvider):
        def __init__(self) -> None:
            super().__init__(delays_enabled=False)
            self.review_contexts: list[Any] = []
            self.optimizer_contexts: list[Any] = []

        async def generate_review(self, **kwargs: Any):  # type: ignore[no-untyped-def,override]
            self.review_contexts.append((kwargs["iteration"], kwargs.get("context")))
            return await super().generate_review(**kwargs)

        async def generate_revision_plan(self, **kwargs: Any):  # type: ignore[no-untyped-def,override]
            self.optimizer_contexts.append(kwargs.get("context"))
            return await super().generate_revision_plan(**kwargs)

    provider = Capturing()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a podcast micro-subscription product.",
            user_constraints="Mobile-first, no ads.",
        )
    )
    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    first_round = [ctx for iteration, ctx in provider.review_contexts if iteration == 1]
    assert len(first_round) == 3
    for context in first_round:
        assert context.requirements.user_constraints == "Mobile-first, no ads."
        assert context.previous_findings == []
    second_round = [
        ctx for iteration, ctx in provider.review_contexts if iteration == 2
    ]
    assert all(ctx.previous_findings for ctx in second_round)

    (context,) = provider.optimizer_contexts
    assert context.prd == result.versions[0].content
    assert context.baseline_version == 1
    ids = [item["finding_id"] for item in context.findings]
    assert len(ids) == len(set(ids))
    assert len(ids) == len(result.versions[0].evaluation.combined_feedback)  # type: ignore[union-attr]

    # Every v1 finding has a v2 status, and v2's plan cites v1 finding ids.
    v2 = result.versions[1]
    assert v2.evaluation is not None and v2.revision_plan is not None
    statuses = {item.status for item in v2.evaluation.finding_resolutions}
    assert FindingStatus.RESOLVED in statuses
    assert all(
        item.source_finding_ids or RevisionSource.USER in item.source_roles
        for item in v2.revision_plan.items
    )
    assert v2.quality is not None and v2.quality.structure_complete
