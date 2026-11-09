from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from prd_benchmark._yaml import dump_yaml, load_yaml
from prd_benchmark.artifacts import ArtifactExistsError, BatchLayout
from prd_benchmark.cases import Case
from prd_benchmark.cli import main
from prd_benchmark.pipeline import load_blind_map
from prd_benchmark.review import (
    adjudicate,
    disagreements,
    export_review_package,
    package_leaks,
    submit_review,
)


class _SeededRandom(random.Random):
    """Deterministic stand-in for SystemRandom in tests."""


@pytest.fixture
def judged(output_root: Path) -> BatchLayout:
    assert main(["run", "--batch-id", "rv-batch", "--output-root", str(output_root),
                 "--cases", "PQB-P01", "PQB-P06"]) == 0  # fmt: skip
    assert main(["judge", "--batch-id", "rv-batch", "--output-root",
                 str(output_root)]) == 0  # fmt: skip
    return BatchLayout(output_root, "rv-batch")


def test_package_hides_conditions_and_judge_data(
    judged: BatchLayout, cases: dict[str, Case]
) -> None:
    entries = export_review_package(judged, cases, rng=_SeededRandom(7))  # type: ignore[arg-type]
    package = judged.review / "package"
    assert package_leaks(judged, entries) == []
    names = {p.name for p in package.rglob("*")}
    assert {
        "README.md",
        "order.json",
        "prd.md",
        "requirement.md",
        "scoresheet.yaml",
    } <= names
    doc_ids = {b.doc_id for b in load_blind_map(judged)}
    for path in package.rglob("*"):
        assert not any(d in str(path) for d in doc_ids)
    # The mapping exists, but outside the package.
    mapping = json.loads((judged.review / "private" / "mapping.json").read_text())
    assert {e["doc_id"] for e in mapping["entries"]} == doc_ids
    assert not str(judged.review / "private").startswith(str(package))
    readme = (package / "README.md").read_text(encoding="utf-8")
    assert "不能保证完全盲化" in readme


def test_review_ids_are_random_and_order_is_shuffled(
    judged: BatchLayout, cases: dict[str, Case]
) -> None:
    entries = export_review_package(judged, cases, rng=_SeededRandom(3))  # type: ignore[arg-type]
    order = json.loads((judged.review / "package" / "order.json").read_text())["order"]
    assert sorted(order) == sorted(e.review_id for e in entries)
    assert all(e.review_id.startswith("r-") and len(e.review_id) == 10 for e in entries)
    with pytest.raises(ArtifactExistsError):
        export_review_package(judged, cases)


def test_leak_check_catches_a_planted_label(
    judged: BatchLayout, cases: dict[str, Case]
) -> None:
    entries = export_review_package(judged, cases, rng=_SeededRandom(1))  # type: ignore[arg-type]
    sheet = next((judged.review / "package").rglob("scoresheet.yaml"))
    sheet.write_text(
        sheet.read_text(encoding="utf-8") + "\nnote: B.best\n", encoding="utf-8"
    )
    assert any("B.best" in leak for leak in package_leaks(judged, entries))


def test_submissions_lock_and_disagreements_need_adjudication(
    judged: BatchLayout, cases: dict[str, Case], tmp_path: Path
) -> None:
    entries = export_review_package(judged, cases, rng=_SeededRandom(5))  # type: ignore[arg-type]
    review_id = entries[0].review_id
    blank = load_yaml(
        judged.review / "package" / "docs" / review_id / "scoresheet.yaml"
    )
    first_item = next(iter(blank["items"]))

    def filled(verdict: str) -> Path:
        sheet = json.loads(json.dumps(blank))
        sheet["items"][first_item]["verdict"] = verdict
        path = tmp_path / f"{verdict}.yaml"
        path.write_text(dump_yaml(sheet), encoding="utf-8")
        return path

    submit_review(judged, "alice", review_id, filled("covered"))
    with pytest.raises(ArtifactExistsError):  # locked once submitted
        submit_review(judged, "alice", review_id, filled("missing"))
    submit_review(judged, "bob", review_id, filled("partial"))
    found = disagreements(judged, review_id)
    assert found == {f"items.{first_item}": {"alice": "covered", "bob": "partial"}}
    with pytest.raises(ValueError, match="undecided"):
        adjudicate(judged, review_id, "carol", {})
    adjudicate(judged, review_id, "carol", {f"items.{first_item}": "partial"})
    with pytest.raises(ArtifactExistsError):
        adjudicate(judged, review_id, "carol", {f"items.{first_item}": "covered"})
    with pytest.raises(ValueError):
        submit_review(judged, "Not A Name", review_id, filled("covered"))
