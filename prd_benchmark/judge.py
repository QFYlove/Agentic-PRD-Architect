"""Judge output contract, parsing, structural validation, and the Mock Judge.

No real judge exists yet. The Mock Judge produces schema-valid output so the
evidence, scoring, and reporting pipeline can be exercised end to end; its
verdicts are derived from hashes and carry no information about quality.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from prd_benchmark.cases import Case

Verdict = Literal["covered", "partial", "missing", "contradicted"]
#: ``general``: a material conflict with the input that changes behaviour or
#: implementation. ``internal``: the document contradicts itself about this
#: item; it belongs to the consistency dimension and never caps correctness.
#: A violation of an explicit H entry is not a kind: it is a separate
#: ``hard_constraint_claim``, so the item's own verdict remains the assessment
#: that applies when a human rejects the claim.
ContradictionKind = Literal["general", "internal"]
#: Lowercase slug naming one underlying defect, reused across items and passes.
DEFECT_KEY_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$"
DimensionName = Literal[
    "correctness", "flow", "exceptions", "acceptance", "consistency"
]
DIMENSIONS: tuple[DimensionName, ...] = (
    "correctness",
    "flow",
    "exceptions",
    "acceptance",
    "consistency",
)
MOCK_JUDGE_ID = "mock-judge-v1"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HardConstraintClaim(_Strict):
    """The judge's claim that the document violates one explicit H entry.

    Only a claim that cites an H id of the case, whose quotes are found in the
    document, and whose ``behavior_impact`` passes the grounding check becomes
    a pending candidate. It never decides the score by itself: a human confirms
    or rejects it.
    """

    violated_constraint: str = Field(min_length=1)
    quotes: tuple[str, ...] = Field(min_length=1)
    behavior_impact: str = Field(min_length=1)
    defect_key: str = Field(pattern=DEFECT_KEY_PATTERN)


class ItemJudgment(_Strict):
    item_id: str = Field(pattern=r"^[RC]\d+$")
    #: The assessment of the item on its own. When a hard-constraint claim is
    #: attached, this is what stands if a human rejects the claim.
    verdict: Verdict
    evidence_quotes: tuple[str, ...] = ()
    rationale: str = Field(min_length=1)
    contradiction_kind: ContradictionKind | None = None
    #: Required for every contradiction: which business behaviour or
    #: implementation differs, citing the text in 「」. A pure wording
    #: difference has no answer here and is therefore not a contradiction.
    behavior_impact: str | None = None
    #: Required for every contradiction. Judgments that stem from the same
    #: underlying defect share a key, so the defect is counted once.
    defect_key: str | None = Field(default=None, pattern=DEFECT_KEY_PATTERN)
    #: Required for a ``general`` contradiction: the non-H rule it conflicts
    #: with (this item's id, another R/C id, or an explicit/derived L id).
    rule_basis: tuple[str, ...] = ()
    hard_constraint_claim: HardConstraintClaim | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.verdict != "missing" and not self.evidence_quotes:
            raise ValueError(f"{self.item_id}: {self.verdict} needs evidence")
        if self.verdict == "contradicted":
            if self.contradiction_kind is None:
                raise ValueError(f"{self.item_id}: contradiction needs a kind")
            if not (self.behavior_impact and self.behavior_impact.strip()):
                raise ValueError(
                    f"{self.item_id}: contradiction needs a behavior_impact"
                )
            if self.defect_key is None:
                raise ValueError(f"{self.item_id}: contradiction needs a defect_key")
            if self.contradiction_kind == "general" and not self.rule_basis:
                raise ValueError(f"{self.item_id}: general contradiction needs basis")
        elif (
            self.contradiction_kind is not None
            or self.behavior_impact is not None
            or self.defect_key is not None
            or self.rule_basis
        ):
            raise ValueError(f"{self.item_id}: only contradictions carry a kind")
        return self


class Defect(_Strict):
    description: str = Field(min_length=1)
    quote: str | None = None
    related_item: str | None = None


class DimensionJudgment(_Strict):
    dimension: DimensionName
    anchor: int = Field(ge=0, le=4)
    evidence_quotes: tuple[str, ...] = ()
    defects: tuple[Defect, ...] = ()

    @model_validator(mode="after")
    def justified(self) -> Self:
        if self.anchor < 4 and not self.defects:
            raise ValueError(f"{self.dimension}: anchor < 4 needs a defect")
        return self


class CriticalCandidate(_Strict):
    rule_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class JudgeOutput(_Strict):
    """What a judge may return. No field for a total score exists on purpose."""

    judge_id: str = Field(min_length=1)
    items: tuple[ItemJudgment, ...]
    clarifications: tuple[ItemJudgment, ...] = ()
    dimensions: tuple[DimensionJudgment, ...]
    critical_candidates: tuple[CriticalCandidate, ...] = ()


class JudgeParseError(ValueError):
    """The raw judge response is not one schema-valid JSON object."""


_FENCE = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


def parse_judge_response(raw: str) -> JudgeOutput:
    """Parse a raw judge reply: exactly one JSON object, optionally fenced.

    Anything else -- prose around the object, several objects, a list, extra
    fields such as a total score -- is rejected rather than repaired, so a
    judge cannot smuggle an unvalidated number into the pipeline.
    """
    text = raw.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise JudgeParseError(f"not valid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise JudgeParseError("top-level value is not a JSON object")
    try:
        return JudgeOutput.model_validate(value)
    except ValidationError as error:
        raise JudgeParseError(f"schema violation: {error}"[:2000]) from error


def structural_problems(output: JudgeOutput, case: Case) -> list[str]:
    """Mismatches with the case that make a judge output unusable."""
    problems: list[str] = []
    expected_r = [item.id for item in case.required_items]
    expected_c = [item.id for item in case.clarifications]
    got_r = [item.item_id for item in output.items]
    got_c = [item.item_id for item in output.clarifications]
    if sorted(got_r) != sorted(expected_r) or len(set(got_r)) != len(got_r):
        problems.append(f"items {got_r} do not match {expected_r}")
    if sorted(got_c) != sorted(expected_c) or len(set(got_c)) != len(got_c):
        problems.append(f"clarifications {got_c} do not match {expected_c}")
    dims = [d.dimension for d in output.dimensions]
    if sorted(dims) != sorted(DIMENSIONS):
        problems.append(f"dimensions {dims} are not exactly {list(DIMENSIONS)}")
    allowed = case.critical_rule_ids
    for candidate in output.critical_candidates:
        if candidate.rule_id not in allowed:
            problems.append(f"unknown critical rule {candidate.rule_id}")
    return problems


@dataclass(frozen=True)
class JudgeRequest:
    doc_id: str
    case: Case
    document: str
    judge_pass: int
    item_order: tuple[str, ...]


class Judge(Protocol):
    judge_id: str

    async def evaluate(self, request: JudgeRequest) -> JudgeOutput: ...


def _bucket(*parts: str, modulo: int) -> int:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulo


class MockJudge:
    """Deterministic, schema-valid judge for dry runs. Not a quality signal."""

    judge_id = MOCK_JUDGE_ID

    def _quote(self, document: str, key: str) -> str:
        lines = [line.strip() for line in document.splitlines()]
        usable = [line for line in lines if len(line) >= 4]
        if not usable:
            return document.strip()[:20]
        return usable[_bucket(key, modulo=len(usable))][:30]

    async def evaluate(self, request: JudgeRequest) -> JudgeOutput:
        doc_key = hashlib.sha256(request.document.encode("utf-8")).hexdigest()
        verdicts: tuple[Verdict, ...] = ("covered", "partial", "missing")

        def judge_item(item_id: str) -> ItemJudgment:
            verdict = verdicts[_bucket(doc_key, item_id, modulo=3)]
            quotes = (
                ()
                if verdict == "missing"
                else (self._quote(request.document, doc_key + item_id),)
            )
            return ItemJudgment(
                item_id=item_id,
                verdict=verdict,
                evidence_quotes=quotes,
                rationale="Mock judge: hash-derived verdict, not an assessment.",
            )

        r_ids = [i for i in request.item_order if i.startswith("R")]
        c_ids = [i for i in request.item_order if i.startswith("C")]
        dimensions = []
        for name in DIMENSIONS:
            anchor = 2 + _bucket(doc_key, name, modulo=3)
            quote = self._quote(request.document, doc_key + name)
            defects = (
                ()
                if anchor == 4
                else (Defect(description="Mock judge defect.", quote=quote),)
            )
            dimensions.append(
                DimensionJudgment(
                    dimension=name,
                    anchor=anchor,
                    evidence_quotes=(quote,),
                    defects=defects,
                )
            )
        return JudgeOutput(
            judge_id=self.judge_id,
            items=tuple(judge_item(i) for i in r_ids),
            clarifications=tuple(judge_item(i) for i in c_ids),
            dimensions=tuple(dimensions),
        )
