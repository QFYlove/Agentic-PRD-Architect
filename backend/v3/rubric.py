"""V3 reviewer rubrics.

The UX, Tech and Biz dimensions are the V2 ones, so a V3 score for those roles
means what it meant before. The Product Reviewer is new in V3 and gets its own
four dimensions. The V2 rubric module is not changed: ``contracts/v1`` mirrors
it and must stay byte-for-byte the same.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal

from backend.rubric import (
    DIMENSION_SCORE_MAX,
    ROLE_RUBRICS,
    SCORE_ANCHORS,
    RubricDimension,
)
from backend.schemas import DimensionScoreInput
from backend.v3.models import Reviewer

RUBRIC_VERSION = "v3-2026-11"
SCORING_VERSION = "weighted-mean-v1"

PRODUCT_DIMENSIONS: tuple[RubricDimension, ...] = (
    RubricDimension(
        "problem_fit",
        "问题定义与用户匹配",
        "Problem definition and user fit",
        0.30,
        "Is the user problem stated precisely, and do the target users and "
        "features actually match it?",
    ),
    RubricDimension(
        "solution_soundness",
        "产品方案合理性",
        "Soundness of the solution",
        0.25,
        "Is the chosen solution a reasonable answer to the problem, with "
        "alternatives considered and each feature necessary?",
    ),
    RubricDimension(
        "completeness_consistency",
        "需求完整性与逻辑一致性",
        "Completeness and logical consistency",
        0.25,
        "Are business rules complete, traceable to requirements, and free of "
        "contradictions between sections?",
    ),
    RubricDimension(
        "scope_priority",
        "MVP 范围与优先级",
        "MVP scope and priority",
        0.20,
        "Is the MVP scope consistent with the goals and constraints, with "
        "priorities that hold up?",
    ),
)

RUBRICS: dict[Reviewer, tuple[RubricDimension, ...]] = {
    Reviewer.PRODUCT: PRODUCT_DIMENSIONS,
    Reviewer.UX: ROLE_RUBRICS["ux"],
    Reviewer.TECH: ROLE_RUBRICS["tech"],
    Reviewer.BIZ: ROLE_RUBRICS["biz"],
}

#: Categories each reviewer may raise. A finding outside its reviewer's list is
#: another reviewer's job and is dropped, so one role cannot stand in for another.
CATEGORIES: dict[Reviewer, frozenset[str]] = {
    Reviewer.PRODUCT: frozenset(
        {
            "requirement_gap",
            "logic_error",
            "contradiction",
            "scope_priority",
            "traceability",
            "alternative",
            "constraint_violation",
            "unsupported_claim",
            "other",
        }
    ),
    Reviewer.UX: frozenset(
        {
            "missing_flow",
            "edge_case",
            "state_feedback",
            "ux_clarity",
            "recovery",
            "other",
        }
    ),
    Reviewer.TECH: frozenset(
        {
            "technical_risk",
            "data_integrity",
            "interface",
            "state_machine",
            "performance",
            "security_privacy",
            "reliability",
            "edge_case",
            "other",
        }
    ),
    Reviewer.BIZ: frozenset(
        {
            "business_value",
            "positioning",
            "business_model",
            "cost_risk",
            "operation_risk",
            "compliance",
            "scope_priority",
            "unsupported_claim",
            "quantification",
            "other",
        }
    ),
}

REVIEWER_LABELS: dict[Reviewer, str] = {
    Reviewer.ANALYST: "产品分析",
    Reviewer.PRODUCT: "产品",
    Reviewer.UX: "体验",
    Reviewer.TECH: "技术",
    Reviewer.BIZ: "商业",
}


def resolve_dimension(reviewer: Reviewer, value: str) -> str | None:
    needle = value.strip().casefold()
    for dimension in RUBRICS[reviewer]:
        if needle in {
            dimension.id.casefold(),
            dimension.label_zh.casefold(),
            dimension.label_en.casefold(),
        }:
            return dimension.id
    return None


def reviewer_score(
    reviewer: Reviewer, scores: Sequence[DimensionScoreInput]
) -> int | None:
    """``Σ(score / 5 × weight) × 100``; ``None`` when a dimension is missing.

    A missing dimension is reported as no score rather than guessed.
    """
    by_id: dict[str, int] = {}
    for item in scores:
        resolved = resolve_dimension(reviewer, item.dimension)
        if resolved is not None:
            by_id[resolved] = item.score
    total = Decimal(0)
    for dimension in RUBRICS[reviewer]:
        if dimension.id not in by_id:
            return None
        total += (
            Decimal(by_id[dimension.id])
            / Decimal(DIMENSION_SCORE_MAX)
            * Decimal(str(dimension.weight))
        )
    return int((total * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def rubric_block(reviewer: Reviewer) -> str:
    lines = [f"RUBRIC ({reviewer.value}) -- score each dimension id exactly once:"]
    for dimension in RUBRICS[reviewer]:
        lines.append(
            f"- `{dimension.id}` ({dimension.label_en} / {dimension.label_zh}, "
            f"weight {round(dimension.weight * 100)}%): {dimension.focus}"
        )
    lines.append(
        "Anchors: "
        + "; ".join(
            f"{score} = {text['en']}" for score, text in sorted(SCORE_ANCHORS.items())
        )
    )
    return "\n".join(lines)


def rubric_document() -> dict[str, object]:
    return {
        "rubric_version": RUBRIC_VERSION,
        "scoring_version": SCORING_VERSION,
        "formula": "ReviewerScore = Σ(DimensionScore / 5 × Weight) × 100",
        "aggregate": "none -- the four reviewers are shown separately",
        "anchors": {str(score): text for score, text in SCORE_ANCHORS.items()},
        "reviewers": {
            reviewer.value: {
                "label": REVIEWER_LABELS[reviewer],
                "categories": sorted(CATEGORIES[reviewer]),
                "dimensions": [
                    {
                        "id": d.id,
                        "label_zh": d.label_zh,
                        "label_en": d.label_en,
                        "weight": d.weight,
                    }
                    for d in dimensions
                ],
            }
            for reviewer, dimensions in RUBRICS.items()
        },
    }


def _check() -> None:
    for reviewer, dimensions in RUBRICS.items():
        total = round(sum(d.weight for d in dimensions), 6)
        if total != 1.0:
            raise ValueError(f"V3 rubric weights for {reviewer} sum to {total}")


_check()
