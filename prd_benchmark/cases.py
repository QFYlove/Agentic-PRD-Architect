"""Frozen test cases, their gold standards, and the case manifest."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.schemas import CreateRunRequest
from prd_benchmark._yaml import load_yaml

if TYPE_CHECKING:
    from prd_benchmark.config import PilotConfig

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CASES_DIR = PACKAGE_DIR / "cases"
#: Human-calibration cases (P91, P92): never part of a Pilot batch.
CALIBRATION_CASES_DIR = PACKAGE_DIR / "calibration_set" / "cases"
CALIBRATION_BATCH_PREFIX = "cal-"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HardConstraint(_Strict):
    """An explicit, checkable constraint stated in the frozen input.

    ``quote`` must appear verbatim (whitespace aside) in the frozen input; the
    case refuses to load otherwise. Only these entries can back an automatic
    hard-constraint violation candidate.
    """

    id: str = Field(pattern=r"^H\d+$")
    text: str = Field(min_length=1)
    quote: str = Field(min_length=4)
    note: str | None = None


class RuleRelation(_Strict):
    """How two or more rules of a case interact.

    - ``explicit``: stated in the frozen input; may cite H entries.
    - ``derived``: follows from explicit rules by reasoning. A judge may use it
      to explain a verdict, but it is never a hard constraint by itself.
    - ``design_choice``: the input leaves it open; every listed alternative
      (and any other reasonable, stated one) is acceptable.
    """

    id: str = Field(pattern=r"^L\d+$")
    kind: Literal["explicit", "derived", "design_choice"]
    text: str = Field(min_length=1)
    source_quotes: tuple[str, ...] = ()
    reasoning: str = Field(min_length=1)
    constraints: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def well_formed(self) -> Self:
        if self.kind in {"explicit", "derived"} and not self.source_quotes:
            raise ValueError(f"{self.id}: {self.kind} relations need source quotes")
        if self.kind == "design_choice" and not self.alternatives:
            raise ValueError(f"{self.id}: design choices need alternatives")
        if self.kind != "explicit" and self.constraints:
            raise ValueError(f"{self.id}: only explicit relations may cite H ids")
        return self


class RequiredItem(_Strict):
    id: str = Field(pattern=r"^R\d+$")
    text: str = Field(min_length=1)
    source: Literal["E", "D", "ED"]
    core: bool
    check: str = Field(min_length=1)
    rationale: str | None = None
    impact: str | None = None

    @model_validator(mode="after")
    def justified(self) -> Self:
        if self.source != "E" and not self.rationale:
            raise ValueError(f"{self.id}: derived items need a rationale")
        if self.core and not self.impact:
            raise ValueError(f"{self.id}: core items must state their impact")
        return self

    @property
    def weight(self) -> int:
        return 2 if self.core else 1


class Clarification(_Strict):
    id: str = Field(pattern=r"^C\d+$")
    question: str = Field(min_length=1)
    core: bool
    accept: str = Field(min_length=1)
    not_counted: str | None = None
    impact: str | None = None

    @model_validator(mode="after")
    def justified(self) -> Self:
        if self.core and not self.impact:
            raise ValueError(f"{self.id}: core clarifications must state impact")
        return self


class CriticalDefect(_Strict):
    id: str = Field(pattern=r"^P\d{2}-X\d+$")
    condition: str = Field(min_length=1)


class Conflict(_Strict):
    """Two requirements of the input that cannot both be met.

    Neither side is a hard constraint: a document that names the conflict,
    explains the trade-off, and states which side it gives up is graded on
    the listed items, never as violating the abandoned side.
    """

    id: str = Field(pattern=r"^K\d+$")
    sides: tuple[str, str]
    items: tuple[str, ...] = Field(min_length=1)


class FrozenInput(_Strict):
    user_idea: str
    target_audience: str | None = None
    user_constraints: str | None = None

    def to_request(self) -> CreateRunRequest:
        """The product's own request model, so A and B see identical inputs.

        ``CreateRunRequest`` normalises the text (stripping, empty-to-None);
        building both conditions from its output means the generator receives
        byte-identical fields whichever path called it.
        """
        return CreateRunRequest(
            user_idea=self.user_idea,
            target_audience=self.target_audience,
            user_constraints=self.user_constraints,
        )

    def normalized_text(self) -> str:
        parts = (self.user_idea, self.target_audience, self.user_constraints)
        return "\n".join(normalize_whitespace(p) for p in parts if p)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class Case(_Strict):
    id: str = Field(pattern=r"^PQB-P\d{2}$")
    title: str
    category: str
    case_version: str
    status: Literal["draft", "frozen"]
    frozen_input: FrozenInput
    evaluator_context: str
    hard_constraints: tuple[HardConstraint, ...]
    rule_relations: tuple[RuleRelation, ...] = ()
    conflicts: tuple[Conflict, ...] = ()
    required_items: tuple[RequiredItem, ...]
    clarifications: tuple[Clarification, ...] = ()
    acceptable_assumptions: tuple[str, ...] = ()
    critical_defects: tuple[CriticalDefect, ...]
    judge_notes: str

    @model_validator(mode="after")
    def consistent(self) -> Self:
        groups: list[list[str]] = [
            [h.id for h in self.hard_constraints],
            [r.id for r in self.rule_relations],
            [k.id for k in self.conflicts],
            [r.id for r in self.required_items],
            [c.id for c in self.clarifications],
            [x.id for x in self.critical_defects],
        ]
        for ids in groups:
            if len(ids) != len(set(ids)):
                raise ValueError(f"{self.id}: duplicate ids {ids}")
        if not self.required_items:
            raise ValueError(f"{self.id}: at least one required item")
        prefix = self.id.removeprefix("PQB-") + "-X"
        for defect in self.critical_defects:
            if not defect.id.startswith(prefix):
                raise ValueError(f"{self.id}: defect {defect.id} has wrong prefix")
        # Raises if the frozen input would be rejected by the product API.
        self.frozen_input.to_request()
        source = self.frozen_input.normalized_text()
        for constraint in self.hard_constraints:
            if normalize_whitespace(constraint.quote) not in source:
                raise ValueError(
                    f"{self.id} {constraint.id}: quote not found in frozen input"
                )
        h_ids = self.hard_constraint_ids
        for relation in self.rule_relations:
            for quote in relation.source_quotes:
                if normalize_whitespace(quote) not in source:
                    raise ValueError(
                        f"{self.id} {relation.id}: quote not found in frozen input"
                    )
            unknown = set(relation.constraints) - h_ids
            if unknown:
                raise ValueError(f"{self.id} {relation.id}: unknown H ids {unknown}")
        r_ids = {item.id for item in self.required_items}
        for conflict in self.conflicts:
            missing = set(conflict.items) - r_ids
            if missing:
                raise ValueError(f"{self.id} {conflict.id}: unknown items {missing}")
        return self

    @property
    def hard_constraint_ids(self) -> frozenset[str]:
        return frozenset(h.id for h in self.hard_constraints)

    @property
    def critical_rule_ids(self) -> frozenset[str]:
        generic = {f"G{n}" for n in range(1, 6)}
        return frozenset(generic | {x.id for x in self.critical_defects})


class ManifestEntry(_Strict):
    id: str
    file: str
    category: str
    status: Literal["draft", "frozen"]
    # Quote hashes in YAML: an all-digit hash would otherwise parse as an int.
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class CaseManifest(_Strict):
    case_set: str
    case_set_version: str
    status: Literal["draft", "frozen"]
    frozen_commit: str | None = None
    cases: tuple[ManifestEntry, ...]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(cases_dir: Path = DEFAULT_CASES_DIR) -> CaseManifest:
    return CaseManifest.model_validate(load_yaml(cases_dir / "manifest.yaml"))


def load_case(path: Path) -> Case:
    return Case.model_validate(load_yaml(path))


def load_cases(cases_dir: Path = DEFAULT_CASES_DIR) -> list[Case]:
    """Load every case listed in the manifest, checking the two agree."""
    manifest = load_manifest(cases_dir)
    cases: list[Case] = []
    for entry in manifest.cases:
        case = load_case(cases_dir / entry.file)
        if case.id != entry.id or case.category != entry.category:
            raise ValueError(f"manifest entry {entry.id} disagrees with {entry.file}")
        if case.status != entry.status:
            raise ValueError(f"{entry.id}: status differs between file and manifest")
        cases.append(case)
    return cases


def freeze_problems(
    cases_dir: Path = DEFAULT_CASES_DIR,
    case_ids: Iterable[str] | None = None,
    config: PilotConfig | None = None,
) -> list[str]:
    """Reasons the cases may not be used for an approved (real) run.

    With ``case_ids`` only those cases must be frozen, each through its own
    freeze manifest (``freeze.py``); the rest of the set may stay draft.
    Without it the whole set must be frozen.
    """
    manifest = load_manifest(cases_dir)
    problems: list[str] = []
    if case_ids is not None:
        from prd_benchmark.freeze import case_freeze_problems

        wanted = set(case_ids)
        entries = {e.id: e for e in manifest.cases}
        for case_id in sorted(wanted - set(entries)):
            problems.append(f"{case_id} is not in the manifest")
        for case_id in sorted(wanted & set(entries)):
            entry = entries[case_id]
            if entry.status != "frozen":
                problems.append(f"{case_id} is {entry.status}")
                continue
            if entry.sha256 is None:
                problems.append(f"{case_id} has no recorded sha256")
            elif entry.sha256 != file_sha256(cases_dir / entry.file):
                problems.append(f"{case_id} sha256 does not match {entry.file}")
            problems.extend(case_freeze_problems(cases_dir, case_id, config))
        return problems
    if manifest.status != "frozen":
        problems.append(f"case set status is {manifest.status}, not frozen")
    if manifest.frozen_commit is None:
        problems.append("case set has no frozen_commit")
    for entry in manifest.cases:
        if entry.status != "frozen":
            problems.append(f"{entry.id} is {entry.status}")
        if entry.sha256 is None:
            problems.append(f"{entry.id} has no recorded sha256")
        elif entry.sha256 != file_sha256(cases_dir / entry.file):
            problems.append(f"{entry.id} sha256 does not match {entry.file}")
    return problems
