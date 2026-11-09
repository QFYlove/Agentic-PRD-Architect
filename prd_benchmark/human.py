"""Human review records: overrides, critical-defect decisions, provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from prd_benchmark._yaml import load_yaml
from prd_benchmark.judge import (
    DEFECT_KEY_PATTERN,
    ContradictionKind,
    DimensionName,
    Verdict,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ItemOverride(_Strict):
    """A reviewer's own judgment of one item; replaces the judge's entirely.

    ``hard_constraint`` records that the reviewer finds a violation of that H
    entry; it acts as an already confirmed candidate. Any judge claim on the
    same item is dropped with the rest of the judge's judgment.
    """

    verdict: Verdict
    contradiction_kind: ContradictionKind | None = None
    rule_basis: tuple[str, ...] = ()
    defect_key: str | None = Field(default=None, pattern=DEFECT_KEY_PATTERN)
    hard_constraint: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.verdict == "contradicted" and self.contradiction_kind is None:
            raise ValueError("a contradicted override needs contradiction_kind")
        if self.verdict != "contradicted" and self.contradiction_kind is not None:
            raise ValueError("only a contradicted override carries a kind")
        return self


class CriticalDecision(_Strict):
    candidate_id: str = Field(min_length=1)
    decision: Literal["confirmed", "rejected"]
    note: str | None = None


class AddedCritical(_Strict):
    rule_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    note: str = Field(min_length=1)


class HumanReview(_Strict):
    """One reviewer's adjudication of one blinded document.

    ``scope: full`` means every R and C item and every dimension was checked;
    only then is the document's score labelled ``human_reviewed``.
    """

    doc_id: str
    reviewer: str = Field(min_length=1)
    scope: Literal["full", "partial"]
    reviewed_items: tuple[str, ...] = ()
    item_overrides: dict[str, ItemOverride] = Field(default_factory=dict)
    dimension_overrides: dict[DimensionName, Annotated[int, Field(ge=0, le=4)]] = Field(
        default_factory=dict
    )
    critical_decisions: tuple[CriticalDecision, ...] = ()
    added_criticals: tuple[AddedCritical, ...] = ()

    @property
    def provenance(self) -> str:
        return "human_reviewed" if self.scope == "full" else "partially_reviewed"


def load_human_review(path: Path) -> HumanReview | None:
    if not path.exists():
        return None
    return HumanReview.model_validate(load_yaml(path))
