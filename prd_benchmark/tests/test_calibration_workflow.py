"""Human calibration on P91/P92, offline: stage -> review package -> roles ->
locked A/B submissions -> (only then) manual judge -> adjudication ->
comparison table. Fixed replies stand in for the judge; no model is called."""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import Any

import pytest

from prd_benchmark import judge_manual, review
from prd_benchmark._yaml import dump_yaml, load_yaml
from prd_benchmark.artifacts import BatchLayout
from prd_benchmark.batch import BatchOptions, run_batch
from prd_benchmark.cases import CALIBRATION_CASES_DIR, Case, load_cases
from prd_benchmark.cli import main
from prd_benchmark.config import PilotConfig
from prd_benchmark.judge import DIMENSIONS
from prd_benchmark.pipeline import load_blind_map
from prd_benchmark.tests.test_judge_manual import ISOLATED, _approved

ROLES = {
    "judge_operator": "judge-operator-tbd",
    "reviewer_a": "reviewer-a-tbd",
    "reviewer_b": "reviewer-b-tbd",
    "adjudicator": "adjudicator-tbd",
}


@pytest.fixture
def cal_cases() -> dict[str, Case]:
    return {c.id: c for c in load_cases(CALIBRATION_CASES_DIR)}


@pytest.fixture
def staged(output_root: Path, cal_cases: dict[str, Case]) -> BatchLayout:
    review.stage_calibration_batch(output_root, "cal-01")
    layout = BatchLayout(output_root, "cal-01")
    review.export_review_package(layout, cal_cases, rng=random.Random(2))  # type: ignore[arg-type]
    judge_manual.export_judge_package(
        layout,
        cal_cases,
        passes=2,
        seed=0,
        rng=random.Random(4),  # type: ignore[arg-type]
    )
    return layout


def _entries(layout: BatchLayout) -> list[dict[str, Any]]:
    data = json.loads((layout.review / "private" / "mapping.json").read_text())
    return list(data["entries"])


def _sheet(layout: BatchLayout, review_id: str, tmp: Path, name: str, r1: str) -> Path:
    sheet = load_yaml(
        layout.review / "package" / "docs" / review_id / "scoresheet.yaml"
    )
    for section in ("items", "clarifications"):
        for value in sheet[section].values():
            value.update(verdict="covered", rationale="ok")
    sheet["items"]["R1"]["verdict"] = r1
    for value in sheet["dimensions"].values():
        value["anchor"] = 3
    path = tmp / f"{name}-{review_id}.yaml"
    path.write_text(dump_yaml(sheet), encoding="utf-8")
    return path


def _reply(case: Case, document: str) -> str:
    quote = next(ln.strip() for ln in document.splitlines() if len(ln.strip()) > 12)

    def item(item_id: str) -> dict[str, Any]:
        return {"item_id": item_id, "verdict": "covered",
                "evidence_quotes": [quote[:30]], "rationale": "r"}  # fmt: skip

    return json.dumps(
        {
            "judge_id": "ide",
            "items": [item(r.id) for r in case.required_items],
            "clarifications": [item(c.id) for c in case.clarifications],
            "dimensions": [{"dimension": d, "anchor": 4} for d in DIMENSIONS],
        },
        ensure_ascii=False,
    )


def test_calibration_package_holds_only_p91_p92_and_leaks_nothing(
    staged: BatchLayout,
) -> None:
    assert {e.case_id for e in load_blind_map(staged)} == {"PQB-P91", "PQB-P92"}
    entries = [
        review.ReviewEntry(
            e["review_id"], e["doc_id"], e["case_id"], tuple(e["labels"])
        )
        for e in _entries(staged)
    ]
    assert review.package_leaks(staged, entries) == []
    assert judge_manual.package_leaks(staged) == []
    sheet = next((staged.review / "package").rglob("scoresheet.yaml"))
    blank = load_yaml(sheet)
    assert set(next(iter(blank["items"].values()))) >= {
        "verdict", "contradiction_kind", "hard_constraint", "quotes"
    }  # fmt: skip


def test_roles_must_be_four_different_people(staged: BatchLayout) -> None:
    with pytest.raises(ValueError, match="four different"):
        review.assign_roles(staged, **{**ROLES, "reviewer_b": ROLES["reviewer_a"]})
    with pytest.raises(ValueError, match="different"):
        review.assign_roles(staged, **{**ROLES, "judge_operator": ROLES["reviewer_a"]})


def test_calibration_order_is_enforced_end_to_end(
    staged: BatchLayout, cal_cases: dict[str, Case], config: PilotConfig,
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    entries = _entries(staged)
    with pytest.raises(ValueError, match="assign roles"):
        review.submit_review(
            staged, ROLES["reviewer_a"], entries[0]["review_id"],
            _sheet(staged, entries[0]["review_id"], tmp_path, "a", "covered"),
        )  # fmt: skip
    review.assign_roles(staged, **ROLES)
    tasks = judge_manual.load_tasks(staged)
    first = next(iter(tasks.values()))
    # Judge sessions cannot start before both reviewers have locked.
    with pytest.raises(judge_manual.ManualJudgeError, match="has not submitted"):
        judge_manual.prepare_session(staged, first.task_id, parent=tmp_path)
    # Only the assigned reviewers may submit; the judge operator may not.
    with pytest.raises(ValueError, match="role"):
        review.submit_review(
            staged, ROLES["judge_operator"], entries[0]["review_id"],
            _sheet(staged, entries[0]["review_id"], tmp_path, "x", "covered"),
        )  # fmt: skip
    for entry in entries:
        rid = entry["review_id"]
        review.submit_review(staged, ROLES["reviewer_a"], rid,
                             _sheet(staged, rid, tmp_path, "a", "covered"))  # fmt: skip
        review.submit_review(staged, ROLES["reviewer_b"], rid,
                             _sheet(staged, rid, tmp_path, "b", "partial"))  # fmt: skip
    # The comparison needs adjudicated disagreements.
    with pytest.raises(ValueError, match="not adjudicated"):
        review.calibration_comparison(staged, cal_cases, passes=2)
    approved = _approved(config, "pilot")
    for task in tasks.values():
        folder = judge_manual.prepare_session(staged, task.task_id, parent=tmp_path)
        blind = next(b for b in load_blind_map(staged) if b.doc_id == task.doc_id)
        document = (staged.runs / blind.path).read_text(encoding="utf-8")
        (folder / "response.json").write_text(
            _reply(cal_cases[task.case_id], document), encoding="utf-8"
        )
        session = {
            "task_id": task.task_id, "judge_input_sha256": task.judge_input_sha256,
            "operator": ROLES["judge_operator"], "isolation": ISOLATED,
        }  # fmt: skip
        if task is first:
            wrong = {**session, "operator": ROLES["reviewer_a"]}
            (folder / "session.yaml").write_text(dump_yaml(wrong), encoding="utf-8")
            with pytest.raises(judge_manual.ManualJudgeError, match="judge operator"):
                judge_manual.import_response(
                    staged, cal_cases, approved, task_id=task.task_id,
                    response_path=folder / "response.json",
                    session_path=folder / "session.yaml",
                )  # fmt: skip
        (folder / "session.yaml").write_text(dump_yaml(session), encoding="utf-8")
        result = judge_manual.import_response(
            staged, cal_cases, approved, task_id=task.task_id,
            response_path=folder / "response.json",
            session_path=folder / "session.yaml",
        )  # fmt: skip
        assert result.valid, result.error
    for entry in entries:
        rid = entry["review_id"]
        assert set(review.disagreements(staged, rid)) == {"items.R1"}
        with pytest.raises(ValueError, match="role"):
            review.adjudicate(staged, rid, ROLES["reviewer_a"], {"items.R1": "covered"})
        review.adjudicate(staged, rid, ROLES["adjudicator"], {"items.R1": "covered"})
    text = review.calibration_comparison(staged, cal_cases, passes=2)
    for heading in ("覆盖判定", "矛盾判定", "严重缺陷", "证据引用", "合理替代方案"):
        assert heading in text
    assert "不是 Judge 的准确率或一致率" in text
    assert "PQB-P92" in text and "R4：人工 covered" in text  # K1 trade-off items
    assert (staged.review / "calibration-comparison.md").exists()
    capsys.readouterr()


def test_calibration_stays_out_of_pilot_batches(
    output_root: Path, config: PilotConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    # A calibration case id is not a Pilot case; cal-* ids are reserved.
    with pytest.raises(ValueError):
        main(["run", "--batch-id", "p-1", "--output-root", str(output_root),
              "--cases", "PQB-P91"])  # fmt: skip
    with pytest.raises(ValueError, match="calibration"):
        options = BatchOptions(
            batch_id="cal-x", mode="fake", output_root=output_root, case_ids=["PQB-P07"]
        )
        asyncio.run(run_batch(options, config))
    # The automatic judge never runs on a calibration batch.
    assert main(["judge", "--batch-id", "cal-x", "--output-root",
                 str(output_root)]) == 2  # fmt: skip
    assert "judge-manual only" in capsys.readouterr().err
    assert not (output_root / "runs" / "cal-x").exists()
