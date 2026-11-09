from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from prd_benchmark.artifacts import ArtifactExistsError, BatchLayout, write_text_once
from prd_benchmark.batch import BatchOptions, run_batch
from prd_benchmark.checks import check_document
from prd_benchmark.cli import EXIT_BLOCKED, main
from prd_benchmark.config import PilotConfig
from prd_benchmark.providers import RealCallsBlockedError, build_real_client


def _run(output_root: Path, *extra: str) -> int:
    return main(["run", "--batch-id", "t-batch", "--output-root", str(output_root),
                 *extra])  # fmt: skip


def test_real_mode_is_refused_before_anything_is_written(
    output_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run(output_root, "--mode", "real", "--confirm-spend",
                "--provider-changelog-date", "2026-10-17")  # fmt: skip
    assert code == EXIT_BLOCKED
    err = capsys.readouterr().err
    assert "real_model_calls is not 'approved'" in err
    assert "is draft" in err
    assert not output_root.exists()


def test_real_judge_is_refused(
    output_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["judge", "--batch-id", "t-batch", "--judge", "claude",
                 "--output-root", str(output_root), "--confirm-spend"])  # fmt: skip
    assert code == EXIT_BLOCKED
    assert "judge_calls is not 'approved'" in capsys.readouterr().err


def test_real_client_refuses_with_any_blocker(config: PilotConfig) -> None:
    with pytest.raises(RealCallsBlockedError):
        build_real_client(config.model, blockers=["not approved"])


async def test_run_batch_rejects_real_mode_directly(
    config: PilotConfig, output_root: Path
) -> None:
    options = BatchOptions(batch_id="t-direct", mode="real", output_root=output_root,
                           confirm_spend=True)  # fmt: skip
    with pytest.raises(RealCallsBlockedError):
        await run_batch(options, config)


def test_fake_pipeline_end_to_end(
    output_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(output_root, "--cases", "PQB-P01", "PQB-P04") == 0
    layout = BatchLayout(output_root, "t-batch")
    for case_id in ("PQB-P01", "PQB-P04"):
        a = layout.run_dir(case_id, "A")
        b = layout.run_dir(case_id, "B")
        assert (a / "output.md").exists()
        assert {p.name for p in b.iterdir()} >= {
            "best.md", "last.md", "v1.md", "snapshot.json", "calls.jsonl",
            "meta.json", "input.json",
        }  # fmt: skip
        calls = [
            json.loads(line) for line in (b / "calls.jsonl").read_text().splitlines()
        ]
        assert calls and all(c["response_model"] == "deepseek-flash" for c in calls)
        a_input = json.loads((a / "input.json").read_text())
        b_input = json.loads((b / "input.json").read_text())
        assert a_input["request"] == b_input["request"]
        assert a_input["case_sha256"] == b_input["case_sha256"]
    batch = json.loads((layout.runs / "batch.json").read_text())
    assert batch["mode"] == "fake" and batch["model"]["model_id"] == "deepseek-flash"
    assert set(batch["condition_orders"]) == {"PQB-P01", "PQB-P04"}

    assert main(["judge", "--batch-id", "t-batch", "--output-root",
                 str(output_root)]) == 0  # fmt: skip
    blind = json.loads((layout.scores / "blind_map.json").read_text())
    labels = sorted(label for d in blind["documents"] for label in d["labels"])
    assert labels.count("A") == 2 and labels.count("B.best") == 2
    # Identical documents share one doc id: B.best == B.last in the fake run.
    assert all(not d["doc_id"].startswith(("A", "B")) for d in blind["documents"])

    assert main(["report", "--batch-id", "t-batch", "--output-root",
                 str(output_root)]) == 0  # fmt: skip
    report = (layout.reports / "t-batch.md").read_text(encoding="utf-8")
    assert "模拟运行" in report and "Mock Judge" in report
    assert "B.best − A" in report and "A − B.v1" in report
    assert "不做显著性判断" in report
    assert "p 值" not in report and "显著提升" not in report
    # Fairness check: A and B.v1 sent the same generator request in every case.
    assert "首次生成请求的哈希一致（同一 prompt、参数与输入）：2/2" in report
    rows = list(csv.DictReader(io.StringIO(
        (layout.reports / "t-batch.csv").read_text(encoding="utf-8")
    )))  # fmt: skip
    assert {r["label"] for r in rows} == {"A", "B.best", "B.last", "B.v1"}
    assert all(r["provenance"] == "auto" for r in rows)

    # A second report is a new revision; nothing is overwritten.
    assert main(["report", "--batch-id", "t-batch", "--output-root",
                 str(output_root)]) == 0  # fmt: skip
    assert (layout.reports / "t-batch.r2.md").exists()
    assert (layout.scores / "doc_scores.r2.json").exists()
    capsys.readouterr()


def test_batches_and_artifacts_are_never_overwritten(output_root: Path) -> None:
    assert _run(output_root, "--cases", "PQB-P01") == 0
    with pytest.raises(FileExistsError):
        _run(output_root, "--cases", "PQB-P01")
    target = output_root / "x.txt"
    write_text_once(target, "first")
    with pytest.raises(ArtifactExistsError):
        write_text_once(target, "second")
    assert target.read_text() == "first"


def test_unsafe_batch_ids_are_rejected(output_root: Path) -> None:
    with pytest.raises(ValueError):
        BatchLayout(output_root, "../escape")


def test_document_checks_are_covariates_only() -> None:
    text = (
        "# 标题\n\n## 小节\n\n- 一\n- 二\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "```mermaid\nflowchart TD\n  A-->B\n```\n"
    )
    checks = check_document(text)
    assert (checks.headings, checks.tables, checks.list_items) == (2, 1, 2)
    assert checks.mermaid_blocks == 1 and checks.code_fences_balanced
    assert not checks.completion_marker_present and not checks.empty
