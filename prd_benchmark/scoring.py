"""Deterministic score aggregation (rubric-v0.4). No model output is a score.

Correctness caps (rubric 4.2), applied by this module only:

- missing core clarifications: 1 -> cap 3, >=2 -> cap 2;
- general contradictions, counted once per ``defect_key``: 1 -> 3, >=2 -> 2;
- confirmed hard-constraint violations: cap 1.

A hard-constraint violation is a *claim* attached to an item, separate from the
item's own verdict. Every pass is scored under explicit scenarios:

- ``base``: no hard-constraint claim applied at all (the judge's item-level
  assessment as it stands without any H adjudication);
- ``if_confirmed``: settled decisions plus every pending claim confirmed;
- ``if_rejected``: settled decisions plus every pending claim rejected;
- ``final``: settled decisions only -- present **only** when nothing is pending.

Confirming a claim zeroes its item's coverage credit and caps correctness at 1.
Rejecting it removes exactly that: the item keeps its own verdict. A general
contradiction tied to a claim (same item or same ``defect_key``) survives a
rejection only if it rests on its own rule basis and its own verified evidence;
otherwise it is flagged for a human and earns nothing and blames nothing.

Internal contradictions (the document disagrees with itself) never cap
correctness; they belong to the consistency dimension.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from statistics import mean
from typing import Any, Literal

from prd_benchmark.cases import Case
from prd_benchmark.evidence import EvidenceIndex, impact_problems, normalize
from prd_benchmark.human import HumanReview
from prd_benchmark.judge import DIMENSIONS, ItemJudgment, JudgeOutput

DIMENSION_WEIGHTS: dict[str, int] = {
    "correctness": 20,
    "flow": 20,
    "exceptions": 15,
    "acceptance": 15,
    "consistency": 5,
}
COVERAGE_WEIGHT = 25
VERDICT_SCORE = {"covered": 1.0, "partial": 0.5, "missing": 0.0, "contradicted": 0.0}
#: The item is addressed, but the document states it two incompatible ways.
INTERNAL_CONTRADICTION_SCORE = 0.5

Decision = Literal["pending", "confirmed", "rejected"]
SCENARIOS = ("base", "if_confirmed", "if_rejected", "final")


@dataclass(frozen=True)
class EffectiveJudgment:
    item_id: str
    verdict: str
    verified: bool
    source: Literal["judge", "human"]
    contradiction_kind: str | None = None
    quote: str | None = None
    quotes: tuple[str, ...] = ()
    defect_key: str | None = None
    rule_basis: tuple[str, ...] = ()
    problem: str | None = None

    @property
    def credited_score(self) -> float:
        # An unverified judgment earns nothing and blames nothing.
        if not self.verified:
            return 0.0
        if self.verdict == "contradicted" and self.contradiction_kind == "internal":
            return INTERNAL_CONTRADICTION_SCORE
        return VERDICT_SCORE[self.verdict]

    @property
    def counts_as_contradiction(self) -> bool:
        return self.verified and self.verdict == "contradicted"

    @property
    def key(self) -> str:
        return self.defect_key or self.item_id


@dataclass(frozen=True)
class EffectiveClaim:
    item_id: str
    violated_constraint: str
    candidate_id: str
    source: Literal["judge", "human"]
    defect_key: str
    quote: str | None = None
    quotes: tuple[str, ...] = ()


@dataclass
class Candidate:
    candidate_id: str
    rule_id: str
    source: Literal["auto_hard_constraint", "judge", "human"]
    quote: str | None
    verified: bool
    item_id: str | None = None
    violated_constraint: str | None = None
    defect_key: str | None = None
    decision: Decision = "pending"
    #: Whether the decision changes the score (hard-constraint claims only).
    affects_score: bool = False
    #: Judge-candidate ids folded into this one (rubric 6.2) and the rule ids
    #: they carried; ``rule_id`` is the one kept.
    aliases: list[str] = field(default_factory=list)
    merged_rule_ids: list[str] = field(default_factory=list)
    #: Where it was found, e.g. ``pass1:R8`` or ``pass2:candidate``.
    occurrences: list[str] = field(default_factory=list)
    #: Why occurrences were merged: ``same_h_and_defect_key`` (claims across
    #: items or passes), ``same_rule_and_quote`` (judge candidates across
    #: passes), ``judge_candidate_same_quote`` (a case rule folded into a claim).
    merge_basis: list[str] = field(default_factory=list)
    #: Signals for the human reviewer. Never acted on automatically.
    review_flags: list[str] = field(default_factory=list)


def candidate_id(rule_id: str, anchor: str | None, quote: str | None) -> str:
    material = f"{rule_id}|{anchor or ''}|{normalize(quote or '')}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:10]


def hard_candidate_id(violated_constraint: str, defect_key: str) -> str:
    """Stable across passes: one H entry violated by one underlying defect."""
    return candidate_id("G1", violated_constraint, defect_key)


@dataclass(frozen=True)
class ScenarioScore:
    coverage_ratio: float
    core_coverage_ratio: float
    correctness_cap: int
    confirmed_claims: int
    general_contradictions: int
    anchors: dict[str, float]
    points: dict[str, float]
    total: float


def basis_problem(rule_basis: tuple[str, ...], case: Case) -> str | None:
    """A general contradiction must rest on a non-H rule of the case.

    H entries are handled by claims; design choices and conflict sides have no
    single correct answer and so cannot be contradicted.
    """
    if not rule_basis:
        return "rule_basis_missing"
    item_ids = {i.id for i in case.required_items} | {c.id for c in case.clarifications}
    relations = {r.id: r.kind for r in case.rule_relations}
    for basis in rule_basis:
        if basis in case.hard_constraint_ids:
            return "basis_is_hard_constraint"
        if basis in relations:
            if relations[basis] == "design_choice":
                return "basis_is_design_choice"
            continue
        if basis.startswith("K"):
            return "basis_is_conflict"
        if basis not in item_ids:
            return "unknown_basis"
    return None


def correctness_cap(missing_core: int, general: int, hard: int) -> int:
    """rubric 4.2: three independent caps; the strictest applies."""
    cap = 4
    if missing_core >= 2:
        cap = min(cap, 2)
    elif missing_core == 1:
        cap = min(cap, 3)
    if general >= 2:
        cap = min(cap, 2)
    elif general == 1:
        cap = min(cap, 3)
    if hard >= 1:
        cap = min(cap, 1)
    return cap


def _ratio(pairs: list[tuple[int, float]]) -> float | None:
    total_weight = sum(weight for weight, _ in pairs)
    if total_weight == 0:
        return None
    return sum(weight * score for weight, score in pairs) / total_weight


def _judge_item(
    judgment: ItemJudgment, case: Case, evidence: EvidenceIndex
) -> tuple[EffectiveJudgment, EffectiveClaim | None, dict[str, Any] | None]:
    """(judgment, valid claim or None, invalid-claim record or None)."""
    valid = tuple(q for q in judgment.evidence_quotes if evidence.check(q).valid)
    problem: str | None = None
    if judgment.verdict != "missing" and not valid:
        problem = "quote_not_found"
    elif judgment.verdict == "contradicted":
        impact = impact_problems(judgment.behavior_impact, evidence)
        if impact:
            problem = impact[0]
        elif judgment.contradiction_kind == "general":
            problem = basis_problem(judgment.rule_basis, case)
    effective = EffectiveJudgment(
        item_id=judgment.item_id,
        verdict=judgment.verdict,
        verified=problem is None,
        source="judge",
        contradiction_kind=judgment.contradiction_kind,
        quote=valid[0] if valid else None,
        quotes=valid,
        defect_key=judgment.defect_key,
        rule_basis=judgment.rule_basis,
        problem=problem,
    )
    claim = judgment.hard_constraint_claim
    if claim is None:
        return effective, None, None
    reasons: list[str] = []
    if claim.violated_constraint not in case.hard_constraint_ids:
        # Only explicit H entries back a violation: L ids (derived or not),
        # conflict ids, and unknown ids are refused here.
        reasons.append("not_explicit_hard_constraint")
    claim_quotes = tuple(q for q in claim.quotes if evidence.check(q).valid)
    if not claim_quotes:
        reasons.append("quote_not_found")
    reasons.extend(impact_problems(claim.behavior_impact, evidence))
    if reasons:
        record = {
            "item_id": judgment.item_id,
            "violated_constraint": claim.violated_constraint,
            "defect_key": claim.defect_key,
            "reasons": reasons,
        }
        return effective, None, record
    return (
        effective,
        EffectiveClaim(
            item_id=judgment.item_id,
            violated_constraint=claim.violated_constraint,
            candidate_id=hard_candidate_id(claim.violated_constraint, claim.defect_key),
            source="judge",
            defect_key=claim.defect_key,
            quote=claim_quotes[0],
            quotes=claim_quotes,
        ),
        None,
    )


def _human_item(
    item_id: str, human: HumanReview, case: Case
) -> tuple[EffectiveJudgment, EffectiveClaim | None, dict[str, Any] | None]:
    override = human.item_overrides[item_id]
    effective = EffectiveJudgment(
        item_id=item_id,
        verdict=override.verdict,
        verified=True,
        source="human",
        contradiction_kind=override.contradiction_kind,
        defect_key=override.defect_key,
        rule_basis=override.rule_basis,
    )
    h = override.hard_constraint
    if h is None:
        return effective, None, None
    if h not in case.hard_constraint_ids:
        record = {
            "item_id": item_id,
            "violated_constraint": h,
            "defect_key": override.defect_key,
            "reasons": ["not_explicit_hard_constraint"],
        }
        return effective, None, record
    key = override.defect_key or item_id.lower() + "-human"
    return (
        effective,
        EffectiveClaim(
            item_id=item_id,
            violated_constraint=h,
            candidate_id=hard_candidate_id(h, key),
            source="human",
            defect_key=key,
        ),
        None,
    )


def _apply_independence(
    judged: list[EffectiveJudgment], claims: list[EffectiveClaim]
) -> list[EffectiveJudgment]:
    """Flag general contradictions that only restate a hard-constraint claim.

    Tied means: on an item that carries a claim, or sharing a claim's
    defect_key. Such a contradiction counts only with verified evidence of its
    own (a quote none of the tied claims uses); its rule basis has already been
    checked to be non-H.
    """
    out: list[EffectiveJudgment] = []
    for j in judged:
        if (
            j.source == "judge"
            and j.counts_as_contradiction
            and j.contradiction_kind == "general"
        ):
            tied = [
                c for c in claims if c.item_id == j.item_id or c.defect_key == j.key
            ]
            if tied:
                used = {normalize(q) for c in tied for q in c.quotes}
                if all(normalize(q) in used for q in j.quotes):
                    j = replace(j, verified=False, problem="depends_on_hard_claim")
        out.append(j)
    return out


class PassScore:
    """One judge pass, scorable under any set of confirmed claim ids."""

    def __init__(
        self,
        judge_pass: int,
        output: JudgeOutput,
        case: Case,
        document: str,
        human: HumanReview | None = None,
    ) -> None:
        evidence = EvidenceIndex(document)
        overrides = human.item_overrides if human else {}
        judged: list[EffectiveJudgment] = []
        claims: list[EffectiveClaim] = []
        invalid: list[dict[str, Any]] = []
        for judgment in [*output.items, *output.clarifications]:
            if judgment.item_id in overrides and human is not None:
                result = _human_item(judgment.item_id, human, case)
            else:
                result = _judge_item(judgment, case, evidence)
            judged.append(result[0])
            if result[1] is not None:
                claims.append(result[1])
            if result[2] is not None:
                invalid.append(result[2])
        self.judge_pass = judge_pass
        self.case = case
        self.judgments = _apply_independence(judged, claims)
        self.claims = claims
        self.invalid_claims = invalid
        self.judge_candidates = [
            Candidate(
                candidate_id=candidate_id(c.rule_id, None, c.quote),
                rule_id=c.rule_id,
                source="judge",
                quote=c.quote,
                verified=evidence.check(c.quote).valid,
            )
            for c in output.critical_candidates
        ]
        by_dimension = {d.dimension: d.anchor for d in output.dimensions}
        dim_overrides = human.dimension_overrides if human else {}
        self.judge_anchors: dict[str, int] = {
            name: dim_overrides.get(name, by_dimension[name]) for name in DIMENSIONS
        }
        c_items = {item.id: item for item in case.clarifications}
        c_judged = [j for j in self.judgments if j.item_id in c_items]
        self.clarification_coverage_ratio = _ratio(
            [(2 if c_items[j.item_id].core else 1, j.credited_score) for j in c_judged]
        )
        self.counts: dict[str, int] = {
            "missing_core_clarifications": sum(
                1
                for j in c_judged
                if j.verified and j.verdict == "missing" and c_items[j.item_id].core
            ),
            "internal_contradictions": sum(
                1
                for j in self.judgments
                if j.counts_as_contradiction and j.contradiction_kind == "internal"
            ),
            "valid_claims": len({c.candidate_id for c in claims}),
            "invalid_claims": len(invalid),
            "unverified_judgments": sum(1 for j in self.judgments if not j.verified),
        }

    @property
    def claim_ids(self) -> frozenset[str]:
        return frozenset(c.candidate_id for c in self.claims)

    def evaluate(self, confirmed: frozenset[str]) -> ScenarioScore:
        r_items = {item.id: item for item in self.case.required_items}
        applied = [c for c in self.claims if c.candidate_id in confirmed]
        violated_items = {c.item_id for c in applied}
        violated_keys = {c.defect_key for c in applied}

        def credit(j: EffectiveJudgment) -> float:
            return 0.0 if j.item_id in violated_items else j.credited_score

        r_judged = [j for j in self.judgments if j.item_id in r_items]
        coverage = _ratio([(r_items[j.item_id].weight, credit(j)) for j in r_judged])
        core = _ratio([(1, credit(j)) for j in r_judged if r_items[j.item_id].core])
        general = {
            j.key
            for j in self.judgments
            if j.counts_as_contradiction and j.contradiction_kind == "general"
        } - violated_keys  # one defect, one count: confirmed claims win
        hard = len({c.candidate_id for c in applied})
        cap = correctness_cap(
            self.counts["missing_core_clarifications"], len(general), hard
        )
        anchors: dict[str, float] = {
            name: float(self.judge_anchors[name]) for name in DIMENSIONS
        }
        anchors["correctness"] = float(min(self.judge_anchors["correctness"], cap))
        points: dict[str, float] = {
            name: DIMENSION_WEIGHTS[name] * anchors[name] / 4 for name in DIMENSIONS
        }
        points["coverage"] = COVERAGE_WEIGHT * (coverage or 0.0)
        return ScenarioScore(
            coverage_ratio=coverage or 0.0,
            core_coverage_ratio=core if core is not None else 0.0,
            correctness_cap=cap,
            confirmed_claims=hard,
            general_contradictions=len(general),
            anchors=anchors,
            points=points,
            total=round(sum(points.values()), 4),
        )


def _mean_scenario(scenarios: list[ScenarioScore]) -> dict[str, Any]:
    names = ["coverage", *DIMENSIONS]
    return {
        "total": round(mean(s.total for s in scenarios), 4),
        "coverage_ratio": round(mean(s.coverage_ratio for s in scenarios), 4),
        "core_coverage_ratio": round(mean(s.core_coverage_ratio for s in scenarios), 4),
        "correctness_caps": [s.correctness_cap for s in scenarios],
        "general_contradictions": [s.general_contradictions for s in scenarios],
        "confirmed_claims": [s.confirmed_claims for s in scenarios],
        "points": {n: round(mean(s.points[n] for s in scenarios), 4) for n in names},
    }


@dataclass
class DocumentScore:
    doc_id: str
    case_id: str
    labels: list[str]
    provenance: str
    passes: list[PassScore] = field(default_factory=list)
    invalid_passes: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    disagreements: list[str] = field(default_factory=list)
    unknown_decisions: list[str] = field(default_factory=list)
    #: Mean over valid passes, keyed by scenario; ``final`` only when settled.
    scenarios: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: For each pending claim: the mean total if only that one were confirmed.
    candidate_effects: dict[str, float] = field(default_factory=dict)
    #: ``pass_status`` is the auxiliary outcome; ``provisional_pass`` mirrors
    #: it as True/False/None (None for pending and unscored).
    pass_status: str = "unscored"
    provisional_pass: bool | None = None

    @property
    def scored(self) -> bool:
        return bool(self.passes)

    @property
    def status(self) -> Literal["unscored", "pending", "final"]:
        """``pending`` while any candidate awaits a human decision."""
        if not self.passes:
            return "unscored"
        return "pending" if self.pending_criticals else "final"

    def total(self, scenario: str = "final") -> float | None:
        values = self.scenarios.get(scenario)
        return None if values is None else float(values["total"])

    @property
    def final_total(self) -> float | None:
        return self.total("final")

    def metric(self, name: str, scenario: str = "final") -> float | None:
        values = self.scenarios.get(scenario)
        return None if values is None else float(values[name])

    def points(self, scenario: str = "final") -> dict[str, float]:
        values = self.scenarios.get(scenario)
        return {} if values is None else dict(values["points"])

    def unverified_problems(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.passes:
            for j in p.judgments:
                if j.problem:
                    counts[j.problem] = counts.get(j.problem, 0) + 1
        return counts

    @property
    def confirmed_criticals(self) -> list[Candidate]:
        return [c for c in self.candidates if c.decision == "confirmed"]

    @property
    def pending_criticals(self) -> list[Candidate]:
        return [c for c in self.candidates if c.decision == "pending"]


def _is_case_rule(rule_id: str) -> bool:
    return not rule_id.startswith("G")


def _foldable(rule_id: str) -> bool:
    """Rules that may be folded into a hard-constraint claim (rubric 6.2).

    A case-specific condition overlapping G1 is counted once; a judge that
    proposes G1 itself duplicates the claim. G2-G5 are different conditions
    and are never folded, even on the same text.
    """
    return _is_case_rule(rule_id) or rule_id == "G1"


def _add(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _collect_candidates(  # noqa: C901 - merge rules are listed one by one
    passes: list[PassScore],
) -> tuple[dict[str, Candidate], dict[str, str]]:
    """Candidates by id across passes, plus judge-candidate alias -> claim id.

    Merge rules, and nothing else:

    1. Claims merge only when H id and ``defect_key`` are both equal (the
       candidate id). Equal H with different keys, or different H with an
       equal key, stay separate.
    2. Judge candidates merge across passes only when rule id and quote are
       both equal (the candidate id).
    3. A verified judge candidate is folded into a claim only when its rule is
       case-specific (or G1), its quote matches the quotes of exactly one
       claim, and no *other* case-specific rule also matches that claim.

    Situations the rules cannot settle are flagged for the reviewer instead
    of being merged: occurrences of one claim that share no quote (the judge
    may have reused a key for two defects), claims with the same H and a
    shared quote under different keys (may be one defect named twice), and
    quote matches that rule 3 refuses.
    """
    merged: dict[str, Candidate] = {}
    quotes_by_claim: dict[str, list[frozenset[str]]] = {}
    for p in passes:
        for c in p.claims:
            candidate = merged.get(c.candidate_id)
            if candidate is None:
                candidate = merged[c.candidate_id] = Candidate(
                    candidate_id=c.candidate_id,
                    rule_id="G1",
                    source="human" if c.source == "human" else "auto_hard_constraint",
                    quote=c.quote,
                    verified=True,
                    item_id=c.item_id,
                    violated_constraint=c.violated_constraint,
                    defect_key=c.defect_key,
                    decision="confirmed" if c.source == "human" else "pending",
                    affects_score=True,
                )
            else:
                _add(candidate.merge_basis, "same_h_and_defect_key")
            candidate.occurrences.append(f"pass{p.judge_pass}:{c.item_id}")
            quotes_by_claim.setdefault(c.candidate_id, []).append(
                frozenset(normalize(q) for q in c.quotes)
            )
    claim_quotes: dict[str, frozenset[str]] = {}
    for cid, groups in quotes_by_claim.items():
        claim_quotes[cid] = frozenset().union(*groups)
        if len(groups) > 1 and not frozenset.intersection(*groups):
            _add(merged[cid].review_flags, "occurrences_share_no_quote")
    claims = [c for c in merged.values() if c.affects_score]
    for a in claims:
        for b in claims:
            if a.candidate_id >= b.candidate_id:
                continue
            if not claim_quotes[a.candidate_id] & claim_quotes[b.candidate_id]:
                continue
            same_h = a.violated_constraint == b.violated_constraint
            flag = "possible_duplicate_of" if same_h else "shares_quote_with"
            _add(a.review_flags, f"{flag}:{b.candidate_id}")
            _add(b.review_flags, f"{flag}:{a.candidate_id}")

    judge: dict[str, Candidate] = {}
    for p in passes:
        for candidate in p.judge_candidates:
            existing = judge.get(candidate.candidate_id)
            if existing is None:
                existing = judge[candidate.candidate_id] = replace(
                    candidate, occurrences=[], merge_basis=[], review_flags=[]
                )
            else:
                _add(existing.merge_basis, "same_rule_and_quote")
            existing.occurrences.append(f"pass{p.judge_pass}:candidate")

    targets: dict[str, list[str]] = {}
    for jid, candidate in judge.items():
        quote = normalize(candidate.quote or "")
        targets[jid] = sorted(
            cid for cid, quotes in claim_quotes.items() if quote in quotes
        )
    case_rules: dict[str, set[str]] = {}
    for jid, matched in targets.items():
        candidate = judge[jid]
        if (
            len(matched) == 1
            and candidate.verified
            and _is_case_rule(candidate.rule_id)
        ):
            case_rules.setdefault(matched[0], set()).add(candidate.rule_id)

    aliases: dict[str, str] = {}
    for jid, candidate in sorted(judge.items()):
        matched = targets[jid]
        refusal: str | None = None
        if not matched:
            merged[jid] = candidate
            continue
        if not candidate.verified:
            refusal = "quote_unverified"
        elif not _foldable(candidate.rule_id):
            refusal = "different_generic_rule"
        elif len(matched) > 1:
            refusal = "matches_several_claims"
        elif len(case_rules.get(matched[0], set())) > 1:
            refusal = "several_case_rules_on_claim"
        if refusal is not None:
            for cid in matched:
                _add(candidate.review_flags, f"shares_quote_with:{cid}:{refusal}")
                _add(merged[cid].review_flags, f"shares_quote_with:{jid}:{refusal}")
            merged[jid] = candidate
            continue
        canonical = merged[matched[0]]
        aliases[jid] = canonical.candidate_id
        _add(canonical.aliases, jid)
        _add(canonical.merge_basis, "judge_candidate_same_quote")
        canonical.occurrences.extend(candidate.occurrences)
        if _is_case_rule(candidate.rule_id) and not _is_case_rule(canonical.rule_id):
            _add(canonical.merged_rule_ids, canonical.rule_id)
            canonical.rule_id = candidate.rule_id
        elif candidate.rule_id != canonical.rule_id:
            _add(canonical.merged_rule_ids, candidate.rule_id)
    return merged, aliases


def aggregate_document(
    *,
    doc_id: str,
    case: Case,
    labels: list[str],
    document: str,
    outputs: list[tuple[int, JudgeOutput | None, list[str]]],
    human: HumanReview | None,
    pass_threshold: float,
) -> DocumentScore:
    """Score each valid pass under every scenario, then average the passes."""
    score = DocumentScore(
        doc_id=doc_id,
        case_id=case.id,
        labels=labels,
        provenance=human.provenance if human else "auto",
    )
    for judge_pass, output, problems in outputs:
        if output is None or problems:
            score.invalid_passes.append(
                {"judge_pass": judge_pass, "problems": problems}
            )
            continue
        score.passes.append(PassScore(judge_pass, output, case, document, human))

    merged, aliases = _collect_candidates(score.passes)
    if human is not None:
        evidence = EvidenceIndex(document)
        for added in human.added_criticals:
            cid = candidate_id(added.rule_id, None, added.quote)
            merged[cid] = Candidate(
                candidate_id=cid,
                rule_id=added.rule_id,
                source="human",
                quote=added.quote,
                verified=evidence.check(added.quote).valid,
                decision="confirmed",
            )
        for decision in human.critical_decisions:
            target = aliases.get(decision.candidate_id, decision.candidate_id)
            candidate = merged.get(target)
            if candidate is None:
                score.unknown_decisions.append(decision.candidate_id)
            elif candidate.source == "human" and candidate.affects_score:
                continue  # a reviewer's own item override is already decided
            else:
                candidate.decision = decision.decision
    score.candidates = sorted(merged.values(), key=lambda c: c.candidate_id)

    claims = [c for c in score.candidates if c.affects_score]
    confirmed = frozenset(c.candidate_id for c in claims if c.decision == "confirmed")
    pending = frozenset(c.candidate_id for c in claims if c.decision == "pending")
    if score.passes:
        scenario_sets = {
            "base": frozenset[str](),
            "if_confirmed": confirmed | pending,
            "if_rejected": confirmed,
        }
        for name, ids in scenario_sets.items():
            score.scenarios[name] = _mean_scenario(
                [p.evaluate(ids) for p in score.passes]
            )
        if not pending:
            # Only score-affecting claims hold the score back; a pending
            # judge-proposed candidate keeps the document status pending.
            score.scenarios["final"] = score.scenarios["if_rejected"]
        for cid in sorted(pending):
            score.candidate_effects[cid] = round(
                mean(p.evaluate(confirmed | {cid}).total for p in score.passes), 4
            )

    if len(score.passes) > 1:
        verdicts: dict[str, set[str]] = {}
        for result in score.passes:
            for j in result.judgments:
                verdicts.setdefault(j.item_id, set()).add(j.verdict)
        score.disagreements = sorted(k for k, v in verdicts.items() if len(v) > 1)

    score.pass_status = pass_status(score, pass_threshold)
    score.provisional_pass = {"pass": True, "fail": False}.get(score.pass_status)
    return score


PassStatus = Literal["unscored", "pending", "pass", "fail"]


def pass_status(score: DocumentScore, pass_threshold: float) -> PassStatus:
    """The auxiliary provisional-pass outcome, separate from the numeric score.

    Any undecided candidate -- G1 claim, G2-G5, or case-specific -- makes it
    ``pending``, even when a final numeric total exists (only G1 claims hold
    the number back). A confirmed critical defect makes it ``fail`` once
    nothing is undecided. Only then does the threshold apply.
    """
    if not score.passes:
        return "unscored"
    if score.pending_criticals or score.final_total is None:
        return "pending"
    if score.confirmed_criticals:
        return "fail"
    return "pass" if score.final_total >= pass_threshold else "fail"
