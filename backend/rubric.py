"""Reviewer rubrics: the one place dimensions, weights, and anchors are defined.

Kept free of model imports on purpose. ``schemas.py`` validates reviewer output
against these definitions, ``scoring.py`` turns dimension scores into role
scores, the prompts quote them to the model, and ``contracts/v1`` mirrors them for
the frontend's 「评分规则」 view -- so a weight changed here changes every one of
those at once, and nowhere else can disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Bumped whenever a dimension, weight, or anchor changes. Stored on every review
#: scored under it, because scores from two rubric versions are not comparable.
RUBRIC_VERSION = "2026-11-v2"

#: Bumped when the arithmetic that turns dimensions into scores changes.
SCORING_VERSION = "weighted-mean-v1"

#: Integer 1-5 per dimension. Anything else is not a score.
DIMENSION_SCORE_MIN = 1
DIMENSION_SCORE_MAX = 5

#: The shared meaning of each point on the 1-5 scale.
SCORE_ANCHORS: dict[int, dict[str, str]] = {
    1: {
        "zh": "缺失、严重错误或无法成立",
        "en": "Missing, seriously wrong, or does not hold up",
    },
    2: {
        "zh": "存在明显缺陷，难以支持落地",
        "en": "Clear defects; cannot support delivery",
    },
    3: {
        "zh": "基本满足，但存在重要缺口",
        "en": "Basically adequate, with important gaps",
    },
    4: {
        "zh": "内容完整，逻辑清晰，具备可执行性",
        "en": "Complete, clear, and executable",
    },
    5: {
        "zh": "内容完整、逻辑严谨，有充分依据",
        "en": "Complete, rigorous, and well supported",
    },
}


@dataclass(frozen=True)
class RubricDimension:
    id: str
    label_zh: str
    label_en: str
    weight: float
    focus: str


ROLE_RUBRICS: dict[str, tuple[RubricDimension, ...]] = {
    "tech": (
        RubricDimension(
            "feasibility",
            "技术可行性",
            "Technical feasibility",
            0.30,
            "Can the specified behaviour be built as written with known "
            "technology, within the stated constraints?",
        ),
        RubricDimension(
            "architecture_data",
            "架构、接口与数据完整性",
            "Architecture, interfaces, and data integrity",
            0.25,
            "Are components, interfaces, data ownership, and consistency rules "
            "defined well enough to implement without guessing?",
        ),
        RubricDimension(
            "reliability",
            "可靠性及异常处理",
            "Reliability and failure handling",
            0.25,
            "Are failure, retry, timeout, idempotency, and recovery behaviours "
            "specified for the core flows?",
        ),
        RubricDimension(
            "security_constraints",
            "安全性与实现约束",
            "Security and implementation constraints",
            0.20,
            "Are security, privacy, compliance, and hard implementation "
            "constraints identified and respected?",
        ),
    ),
    "ux": (
        RubricDimension(
            "needs_fit",
            "用户需求与场景匹配",
            "Fit to user needs and scenarios",
            0.25,
            "Does the product address the problems and scenarios the user "
            "actually described?",
        ),
        RubricDimension(
            "core_flow",
            "核心任务流程",
            "Core task flows",
            0.30,
            "Can a user complete each core task end to end from the steps specified?",
        ),
        RubricDimension(
            "clarity",
            "交互清晰度",
            "Interaction clarity",
            0.25,
            "Are screens, actions, and their priority unambiguous?",
        ),
        RubricDimension(
            "feedback_recovery",
            "状态反馈及异常恢复",
            "State feedback and recovery",
            0.20,
            "Do empty, loading, error, and limit states tell the user what "
            "happened and what to do next?",
        ),
    ),
    "biz": (
        RubricDimension(
            "user_value",
            "用户价值",
            "User value",
            0.30,
            "Is the value to the target user clear and tied to a real problem?",
        ),
        RubricDimension(
            "positioning",
            "产品定位与差异化",
            "Positioning and differentiation",
            0.25,
            "Is it clear why this product, for whom, against which alternatives?",
        ),
        RubricDimension(
            "scope_priority",
            "MVP 范围及优先级",
            "MVP scope and priority",
            0.20,
            "Is the MVP scoped consistently, with priorities that match the "
            "stated goals?",
        ),
        RubricDimension(
            "sustainability",
            "商业模式与成本可持续性",
            "Business model and cost sustainability",
            0.25,
            "Are monetisation and cost drivers identified, with unknowns marked "
            "as assumptions rather than invented figures?",
        ),
    ),
}


def dimensions_for(role: str) -> tuple[RubricDimension, ...]:
    try:
        return ROLE_RUBRICS[role]
    except KeyError as exc:
        raise ValueError(f"Unknown reviewer role: {role}") from exc


def resolve_dimension_id(role: str, value: str) -> str | None:
    """Map what a model wrote for a dimension onto its id.

    Models are shown both the id and the label, and sometimes echo the label
    back. Accepting either avoids a paid repair call for a cosmetic mismatch;
    anything that matches neither is rejected.
    """
    needle = value.strip().casefold()
    for dimension in dimensions_for(role):
        if needle in {
            dimension.id.casefold(),
            dimension.label_zh.casefold(),
            dimension.label_en.casefold(),
        }:
            return dimension.id
    return None


def rubric_document() -> dict[str, object]:
    """The rubric as plain data, for the API and the frontend contract file."""
    return {
        "rubric_version": RUBRIC_VERSION,
        "scoring_version": SCORING_VERSION,
        "scale": {
            "min": DIMENSION_SCORE_MIN,
            "max": DIMENSION_SCORE_MAX,
            "anchors": {str(score): text for score, text in SCORE_ANCHORS.items()},
        },
        "formula": {
            "role": "RoleScore = Σ(DimensionScore / 5 × Weight) × 100",
            "overall": "OverallScore = (Tech + UX + Biz) / 3",
        },
        "gate": {
            "passed": "overall >= quality_threshold AND open must_fix == 0",
            "blocked": "an open must_fix violates a hard constraint the user set",
            "needs_revision": "score below threshold or open must_fix findings",
            "unscored": "a role review is missing its dimension scores",
        },
        "roles": {
            role: [
                {
                    "id": dimension.id,
                    "label_zh": dimension.label_zh,
                    "label_en": dimension.label_en,
                    "weight": dimension.weight,
                    "focus": dimension.focus,
                }
                for dimension in dimensions
            ]
            for role, dimensions in ROLE_RUBRICS.items()
        },
    }


def _check_weights() -> None:
    for role, dimensions in ROLE_RUBRICS.items():
        total = round(sum(dimension.weight for dimension in dimensions), 6)
        if total != 1.0:
            raise ValueError(f"Rubric weights for {role} sum to {total}, not 1.0")
        ids = [dimension.id for dimension in dimensions]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate dimension id in {role} rubric")


_check_weights()
