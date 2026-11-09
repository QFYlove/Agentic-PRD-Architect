from __future__ import annotations

import json

import pytest

from prd_benchmark.calibrate import (
    REQUIRED_COVERAGE,
    Fixture,
    load_fixtures,
    run_fixture,
)
from prd_benchmark.cases import Case
from prd_benchmark.judge import JudgeParseError, parse_judge_response


@pytest.fixture(scope="module")
def fixtures(cases: dict[str, Case]) -> list[Fixture]:
    return load_fixtures(cases)


def test_fixture_set_covers_every_required_situation(
    fixtures: list[Fixture],
) -> None:
    covered = {tag for f in fixtures for tag in f.covers}
    assert REQUIRED_COVERAGE <= covered, sorted(REQUIRED_COVERAGE - covered)
    assert not covered - REQUIRED_COVERAGE, "unknown coverage tags"
    assert len({f.id for f in fixtures}) == len(fixtures)


@pytest.mark.parametrize("fixture_id", [f"CAL-{n:02d}" for n in range(1, 15)])
def test_calibration_fixture(
    fixtures: list[Fixture], cases: dict[str, Case], fixture_id: str
) -> None:
    fixture = next(f for f in fixtures if f.id == fixture_id)
    results = run_fixture(fixture, cases)
    assert results, f"{fixture_id} has no reviews"
    failures = {name: problems for name, problems in results.items() if problems}
    assert not failures, failures


def test_fixture_reviews_cover_all_decision_states(fixtures: list[Fixture]) -> None:
    statuses = set()
    for fixture in fixtures:
        for review in fixture.reviews:
            if "status" in review.expect:
                statuses.add(review.expect["status"])
    assert {"pending", "final", "unscored"} <= statuses


def test_parse_accepts_one_object_optionally_fenced() -> None:
    body = {"judge_id": "x", "items": [], "dimensions": []}
    assert parse_judge_response(json.dumps(body)).judge_id == "x"
    fenced = "```json\n" + json.dumps(body) + "\n```"
    assert parse_judge_response(fenced).judge_id == "x"


@pytest.mark.parametrize(
    ("raw", "needle"),
    [
        ("", "not valid JSON"),
        ('{"judge_id": "x"} trailing', "not valid JSON"),
        ('[{"judge_id": "x"}]', "not a JSON object"),
        ('{"judge_id": "x", "items": [], "dimensions": [], "score": 1}', "schema"),
    ],
)
def test_parse_rejects_anything_else(raw: str, needle: str) -> None:
    with pytest.raises(JudgeParseError, match=needle):
        parse_judge_response(raw)


def test_report_shows_merges_and_kept_rule_ids(
    fixtures: list[Fixture], cases: dict[str, Case]
) -> None:
    from prd_benchmark.calibrate import parse_all
    from prd_benchmark.report import _candidates_section
    from prd_benchmark.scoring import aggregate_document

    fixture = next(f for f in fixtures if f.id == "CAL-14")
    case = cases[fixture.case_id]
    outputs, _ = parse_all(fixture, case)
    score = aggregate_document(
        doc_id="d-cal14", case=case, labels=["A"], document=fixture.document,
        outputs=outputs, human=None, pass_threshold=70,
    )  # fmt: skip
    text = "\n".join(_candidates_section([score]))
    p07 = next(line for line in text.splitlines() if "| P07-X1 |" in line)
    assert "| H7 |" in p07 and "| G1 |" in p07  # kept id, merged id
    assert "judge_candidate_same_quote" in p07
    request_row = next(
        line for line in text.splitlines() if "hold-bypassed-by-request" in line
    )
    assert "pass1:R8, pass2:R2" in request_row
    assert "same_h_and_defect_key" in request_row
    cleanup_row = next(
        line for line in text.splitlines() if "hold-bypassed-by-cleanup" in line
    )
    assert "same_h_and_defect_key" not in cleanup_row
    assert text.count("| G1 | H4 |") == 2  # two H4 defects, not merged
