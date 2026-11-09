"""Offline calibration: fixed judge responses run through the real pipeline.

Each fixture in ``calibration/`` pairs a document with a fixed judge response
and the outcome the scoring rules must produce: schema and parsing, quote and
impact verification, rule-basis checks, defect de-duplication, candidates, and
human decisions. Nothing here calls a model. A fixture checks that the
*pipeline* turns a given judgment into the right score; it says nothing about
whether a real judge would produce that judgment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from prd_benchmark._yaml import load_yaml
from prd_benchmark.cases import PACKAGE_DIR, Case
from prd_benchmark.human import HumanReview
from prd_benchmark.judge import (
    DIMENSIONS,
    JudgeOutput,
    JudgeParseError,
    parse_judge_response,
    structural_problems,
)
from prd_benchmark.scoring import (
    DocumentScore,
    aggregate_document,
    candidate_id,
    hard_candidate_id,
)

DEFAULT_FIXTURES_DIR = PACKAGE_DIR / "calibration"
TOLERANCE = 0.001

#: Situations the fixture set as a whole must exercise (checked by the tests).
REQUIRED_COVERAGE = frozenset(
    {
        "semantic_equivalence",
        "missing",
        "partial",
        "hard_constraint",
        "internal",
        "design_choice",
        "conflict",
        "p07_explicit",
        "p07_derived",
        "p07_design_choice",
        "quote_not_found",
        "quote_mismatch",
        "fabricated_impact",
        "generic_impact",
        "invalid_constraint_ref",
        "duplicate_defect",
        "multiple_candidates",
        "independent_general",
        "dependent_general",
        "pending",
        "confirmed",
        "rejected",
        "parse_error",
        "structural_error",
        "pass_status",
        "merge_same_h_same_defect",
        "no_merge_different_h",
        "no_merge_same_h_different_defect",
        "candidate_merge_report",
    }
)


@dataclass
class Review:
    name: str
    human: dict[str, Any] | None
    expect: dict[str, Any]


@dataclass
class Fixture:
    id: str
    title: str
    case_id: str
    covers: tuple[str, ...]
    document: str
    raw_responses: list[str]
    reviews: list[Review] = field(default_factory=list)
    path: Path | None = None


def _item(item_id: str, spec: dict[str, Any], fill: dict[str, Any]) -> dict[str, Any]:
    merged = {**fill, **spec}
    quote = merged.pop("quote", None)
    item: dict[str, Any] = {
        "item_id": item_id,
        "verdict": merged.pop("verdict"),
        "evidence_quotes": merged.pop("evidence_quotes", [quote] if quote else []),
        "rationale": merged.pop("rationale", "calibration fixture"),
    }
    if item["verdict"] == "missing":
        item["evidence_quotes"] = []
    item.update(merged)
    return item


def expand_response(spec: dict[str, Any], case: Case) -> dict[str, Any]:
    """A full judge response from a compact spec: defaults plus overrides.

    ``fill`` applies to every R and C item unless ``items`` overrides it;
    ``anchors`` is the default dimension anchor. The result is serialised and
    re-parsed by ``parse_judge_response``, exactly like a real reply.
    """
    fill = dict(spec.get("fill", {}))
    overrides: dict[str, dict[str, Any]] = spec.get("items", {})
    order = [i.id for i in case.required_items] + [c.id for c in case.clarifications]
    skip = set(spec.get("omit_items", []))
    judged = [_item(i, overrides.get(i, {}), fill) for i in order if i not in skip]
    default_anchor = int(spec.get("anchors", 4))
    dim_overrides: dict[str, dict[str, Any]] = spec.get("dimensions", {})
    dimensions = []
    for name in DIMENSIONS:
        dim = {
            "dimension": name,
            "anchor": default_anchor,
            **dim_overrides.get(name, {}),
        }
        if dim["anchor"] < 4 and not dim.get("defects"):
            dim["defects"] = [{"description": "calibration fixture defect"}]
        dimensions.append(dim)
    return {
        "judge_id": spec.get("judge_id", "calibration-fixture"),
        "items": [j for j in judged if j["item_id"].startswith("R")],
        "clarifications": [j for j in judged if j["item_id"].startswith("C")],
        "dimensions": dimensions,
        "critical_candidates": spec.get("critical_candidates", []),
    }


def load_fixture(path: Path, cases: dict[str, Case]) -> Fixture:
    data = load_yaml(path)
    case = cases[data["case_id"]]
    raw: list[str] = list(data.get("raw_responses", []))
    for spec in data.get("responses", []):
        raw.append(json.dumps(expand_response(spec, case), ensure_ascii=False))
    reviews = [
        Review(r["name"], r.get("human"), r.get("expect", {}))
        for r in data.get("reviews", [])
    ]
    return Fixture(
        id=data["id"],
        title=data["title"],
        case_id=data["case_id"],
        covers=tuple(data.get("covers", [])),
        document=data["document"],
        raw_responses=raw,
        reviews=reviews,
        path=path,
    )


def load_fixtures(
    cases: dict[str, Case], directory: Path = DEFAULT_FIXTURES_DIR
) -> list[Fixture]:
    return [load_fixture(p, cases) for p in sorted(directory.glob("CAL-*.yaml"))]


def _human(raw: dict[str, Any] | None, doc_id: str) -> HumanReview | None:
    """Resolve fixture decisions to candidate ids.

    ``claim: [H3, defect-key]`` names a hard-constraint claim;
    ``candidate: [P02-X2, quote]`` names a judge-proposed candidate.
    """
    if raw is None:
        return None
    data = {"doc_id": doc_id, "reviewer": "calibration", "scope": "full", **raw}
    decisions = []
    for d in data.pop("decisions", []):
        if "claim" in d:
            h, key = d["claim"]
            cid = hard_candidate_id(h, key)
        elif "candidate" in d:
            rule_id, quote = d["candidate"]
            cid = candidate_id(rule_id, None, quote)
        else:
            cid = d["candidate_id"]
        decisions.append({"candidate_id": cid, "decision": d["decision"]})
    data["critical_decisions"] = decisions
    return HumanReview.model_validate(data)


def parse_all(
    fixture: Fixture, case: Case
) -> tuple[list[tuple[int, JudgeOutput | None, list[str]]], list[str]]:
    outputs: list[tuple[int, JudgeOutput | None, list[str]]] = []
    errors: list[str] = []
    for n, raw in enumerate(fixture.raw_responses, start=1):
        try:
            output = parse_judge_response(raw)
        except JudgeParseError as error:
            errors.append(str(error))
            outputs.append((n, None, ["parse error"]))
            continue
        outputs.append((n, output, structural_problems(output, case)))
    return outputs, errors


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= TOLERANCE


def _candidate_view(score: DocumentScore) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "rule_id": c.rule_id,
                "violated_constraint": c.violated_constraint,
                "decision": c.decision,
                "verified": c.verified,
            }
            for c in score.candidates
        ),
        key=lambda c: (c["rule_id"], str(c["violated_constraint"]), c["decision"]),
    )


def check_review(  # noqa: C901 - one branch per expectation key, kept flat
    fixture: Fixture, case: Case, review: Review
) -> list[str]:
    """Mismatches between one review's expectations and the pipeline outcome."""
    outputs, parse_errors = parse_all(fixture, case)
    expect = review.expect
    problems: list[str] = []
    if "parse_errors" in expect:
        want = expect["parse_errors"]
        if len(parse_errors) != len(want):
            problems.append(f"parse errors {parse_errors} != {want}")
        for got, needle in zip(parse_errors, want, strict=False):
            if needle not in got:
                problems.append(f"parse error {got!r} lacks {needle!r}")
    elif parse_errors:
        problems.append(f"unexpected parse errors {parse_errors}")
    if "structural" in expect:
        got_structural = [p for _, out, ps in outputs if out is not None for p in ps]
        for needle in expect["structural"]:
            if not any(needle in p for p in got_structural):
                problems.append(f"structural problem {needle!r} not found")
    score = aggregate_document(
        doc_id=fixture.id.lower(),
        case=case,
        labels=["calibration"],
        document=fixture.document,
        outputs=outputs,
        human=_human(review.human, fixture.id.lower()),
        pass_threshold=70,
    )
    for key, scenario in (
        ("final_total", "final"),
        ("base_total", "base"),
        ("if_confirmed_total", "if_confirmed"),
        ("if_rejected_total", "if_rejected"),
    ):
        if key in expect and not _close(score.total(scenario), expect[key]):
            problems.append(f"{key} {score.total(scenario)} != {expect[key]}")
    if "status" in expect and score.status != expect["status"]:
        problems.append(f"status {score.status} != {expect['status']}")
    if (
        "provisional_pass" in expect
        and score.provisional_pass != expect["provisional_pass"]
    ):
        problems.append(f"provisional_pass {score.provisional_pass}")
    for scenario, caps in expect.get("correctness_caps", {}).items():
        got_caps = score.scenarios.get(scenario, {}).get("correctness_caps")
        if got_caps != caps:
            problems.append(f"{scenario} caps {got_caps} != {caps}")
    for scenario, counts in expect.get("general_contradictions", {}).items():
        got_general = score.scenarios.get(scenario, {}).get("general_contradictions")
        if got_general != counts:
            problems.append(f"{scenario} general {got_general} != {counts}")
    if score.passes:
        first = score.passes[0]
        for name, value in expect.get("counts", {}).items():
            if first.counts.get(name) != value:
                problems.append(f"count {name} {first.counts.get(name)} != {value}")
        judged = {j.item_id: j for j in first.judgments}
        for item_id, want in expect.get("judgments", {}).items():
            j = judged[item_id]
            for attr, value in want.items():
                if getattr(j, attr) != value:
                    problems.append(f"{item_id}.{attr} {getattr(j, attr)} != {value}")
        for want in expect.get("invalid_claims", []):
            if not any(
                ic["item_id"] == want["item_id"] and want["reason"] in ic["reasons"]
                for ic in first.invalid_claims
            ):
                problems.append(f"invalid claim {want} not reported")
    if "candidates" in expect:
        got_c = _candidate_view(score)
        want_c = sorted(
            ({"verified": True, **c} for c in expect["candidates"]),
            key=lambda c: (
                c["rule_id"],
                str(c.get("violated_constraint")),
                c["decision"],
            ),
        )
        if got_c != want_c:
            problems.append(f"candidates {got_c} != {want_c}")
    if "merged_rule_ids" in expect:
        merged = sorted(r for c in score.candidates for r in c.merged_rule_ids)
        if merged != sorted(expect["merged_rule_ids"]):
            problems.append(f"merged rules {merged} != {expect['merged_rule_ids']}")
    if (
        "unknown_decisions" in expect
        and len(score.unknown_decisions) != expect["unknown_decisions"]
    ):
        problems.append(f"unknown decisions {score.unknown_decisions}")
    if "disagreements" in expect and score.disagreements != expect["disagreements"]:
        problems.append(f"disagreements {score.disagreements}")
    if "pass_status" in expect and score.pass_status != expect["pass_status"]:
        problems.append(f"pass_status {score.pass_status} != {expect['pass_status']}")
    if (
        "candidate_count" in expect
        and len(score.candidates) != expect["candidate_count"]
    ):
        problems.append(f"candidate count {len(score.candidates)}")
    for want in expect.get("candidate_details", []):
        found = [
            c
            for c in score.candidates
            if c.rule_id == want["rule_id"]
            and c.violated_constraint == want.get("violated_constraint")
            and ("defect_key" not in want or c.defect_key == want["defect_key"])
        ]
        if len(found) != 1:
            problems.append(f"candidate {want['rule_id']} found {len(found)} times")
            continue
        c = found[0]
        for attr in ("occurrences", "merged_rule_ids", "merge_basis"):
            if attr in want and sorted(getattr(c, attr)) != sorted(want[attr]):
                problems.append(f"{c.rule_id}.{attr} {getattr(c, attr)}")
        for needle in want.get("review_flags", []):
            if not any(f.startswith(needle) for f in c.review_flags):
                problems.append(f"{c.rule_id} lacks review flag {needle!r}")
        if want.get("no_review_flags") and c.review_flags:
            problems.append(f"{c.rule_id} unexpected flags {c.review_flags}")
    return problems


def run_fixture(fixture: Fixture, cases: dict[str, Case]) -> dict[str, list[str]]:
    case = cases[fixture.case_id]
    return {r.name: check_review(fixture, case, r) for r in fixture.reviews}
