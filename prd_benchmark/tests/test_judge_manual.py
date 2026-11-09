from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest

from prd_benchmark import judge_manual
from prd_benchmark._yaml import dump_yaml, load_yaml
from prd_benchmark.artifacts import ArtifactExistsError, BatchLayout
from prd_benchmark.cases import Case
from prd_benchmark.cli import main
from prd_benchmark.config import PilotConfig
from prd_benchmark.judge import DIMENSIONS
from prd_benchmark.judge_claude import detect_auth, judge_auth_blockers
from prd_benchmark.judge_prompt import output_schema
from prd_benchmark.pipeline import load_blind_map, score_batch

ISOLATED = {k: True for k in judge_manual.Isolation().model_dump()}


def _approved(config: PilotConfig, mode: str = "smoke") -> PilotConfig:
    """An in-memory config with the manual runner approved. Never on disk."""
    return config.model_copy(
        update={
            "approvals": config.approvals.model_copy(
                update={"judge_calls": "approved"}
            ),
            "judge": config.judge.model_copy(
                update={"runner": "manual_ide", "stop_mode": mode}
            ),
        }
    )


@pytest.fixture
def exported(
    output_root: Path, cases: dict[str, Case], config: PilotConfig
) -> BatchLayout:
    assert main(["run", "--batch-id", "mj-batch", "--output-root", str(output_root),
                 "--cases", "PQB-P07"]) == 0  # fmt: skip
    layout = BatchLayout(output_root, "mj-batch")
    judge_manual.export_judge_package(
        layout,
        cases,
        passes=2,
        seed=0,
        rng=random.Random(11),  # type: ignore[arg-type]
    )
    return layout


def _task(
    layout: BatchLayout, judge_pass: int = 1, n: int = 0
) -> judge_manual.JudgeTask:
    tasks = sorted(judge_manual.load_tasks(layout).values(), key=lambda t: t.task_id)
    return [t for t in tasks if t.judge_pass == judge_pass][n]


def _document(layout: BatchLayout, doc_id: str) -> str:
    entry = next(e for e in load_blind_map(layout) if e.doc_id == doc_id)
    return (layout.runs / entry.path).read_text(encoding="utf-8")


def _reply(case: Case, document: str) -> str:
    quote = next(
        line.strip() for line in document.splitlines() if len(line.strip()) > 8
    )

    def item(i: str) -> dict[str, Any]:
        return {"item_id": i, "verdict": "covered", "evidence_quotes": [quote[:30]],
                "rationale": "r"}  # fmt: skip

    return json.dumps(
        {
            "judge_id": "ide",
            "items": [item(i.id) for i in case.required_items],
            "clarifications": [item(c.id) for c in case.clarifications],
            "dimensions": [{"dimension": d, "anchor": 4} for d in DIMENSIONS],
        },
        ensure_ascii=False,
    )


def _session(tmp: Path, task: judge_manual.JudgeTask, **override: Any) -> Path:
    data: dict[str, Any] = {
        "task_id": task.task_id,
        "judge_input_sha256": task.judge_input_sha256,
        "operator": "alice",
        "model_identifier": "claude-opus-5-5",
        "model_identifier_source": "IDE model picker",
        "isolation": ISOLATED,
        **override,
    }
    path = tmp / f"session-{task.task_id}.yaml"
    path.write_text(dump_yaml(data), encoding="utf-8")
    return path


def _import(
    layout: BatchLayout, cases: dict[str, Case], config: PilotConfig, tmp: Path,
    task: judge_manual.JudgeTask, body: str | None = None, **session: Any,
) -> judge_manual.ImportResult:  # fmt: skip
    response = tmp / f"response-{task.task_id}.json"
    if body is None:
        body = _reply(cases[task.case_id], _document(layout, task.doc_id))
    response.write_text(body, encoding="utf-8")
    return judge_manual.import_response(
        layout, cases, config, task_id=task.task_id,
        response_path=response, session_path=_session(tmp, task, **session),
    )  # fmt: skip


# --- export -------------------------------------------------------------------


def test_package_is_anonymous_and_complete(exported: BatchLayout) -> None:
    tasks = judge_manual.load_tasks(exported)
    docs = load_blind_map(exported)
    assert len(tasks) == 2 * len(docs)  # every document, two independent passes
    assert judge_manual.package_leaks(exported) == []
    root = judge_manual.workspace(exported)
    for task in tasks.values():
        folder = root / "package" / "tasks" / task.task_id
        assert sorted(p.name for p in folder.iterdir()) == [
            "judge-input.md", "schema.json", "session.yaml"
        ]  # fmt: skip
        text = (folder / "judge-input.md").read_text(encoding="utf-8")
        for part in ("<system_instructions>", "## 附：Rubric 第 4 节",
                     '"rule_relations"', '"conflicts"', "<document>"):  # fmt: skip
            assert part in text
        assert task.doc_id not in text and task.doc_id not in str(folder)
        assert json.loads((folder / "schema.json").read_text()) == output_schema()
        session = load_yaml(folder / "session.yaml")
        assert session["model_identifier"] == "unknown"
        assert session["input_tokens"] == "unknown" and session["cost_usd"] == "unknown"
        assert not any(session["isolation"].values())
    mapping = (root / "private" / "mapping.json").read_text(encoding="utf-8")
    assert all(t.doc_id in mapping for t in tasks.values())
    # Passes of one document have unrelated ids and a shuffled item order.
    by_doc: dict[str, list[judge_manual.JudgeTask]] = {}
    for t in tasks.values():
        by_doc.setdefault(t.doc_id, []).append(t)
    for pair in by_doc.values():
        first, second = sorted(pair, key=lambda t: t.judge_pass)
        assert first.task_id != second.task_id
        assert first.item_order != second.item_order


def test_export_refuses_to_overwrite(
    exported: BatchLayout, cases: dict[str, Case]
) -> None:
    with pytest.raises(ArtifactExistsError):
        judge_manual.export_judge_package(exported, cases, passes=2, seed=0)


def test_leak_check_catches_a_planted_label(exported: BatchLayout) -> None:
    task = _task(exported)
    path = (
        judge_manual.workspace(exported)
        / "package"
        / "tasks"
        / task.task_id
        / "session.yaml"
    )
    path.write_text(
        path.read_text(encoding="utf-8") + "# from runs/PQB-P07/B/\n", encoding="utf-8"
    )
    assert judge_manual.package_leaks(exported)


def test_session_dir_is_outside_the_repo_and_holds_only_the_task(
    exported: BatchLayout, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _task(exported)
    target = judge_manual.prepare_session(exported, task.task_id, parent=tmp_path)
    assert sorted(p.name for p in target.iterdir()) == [
        "judge-input.md", "schema.json", "session.yaml"
    ]  # fmt: skip
    monkeypatch.setattr(judge_manual, "REPO_ROOT", tmp_path)
    with pytest.raises(judge_manual.ManualJudgeError, match="outside the repository"):
        judge_manual.prepare_session(exported, task.task_id, parent=tmp_path)


# --- import gates ----------------------------------------------------------------


def test_import_is_refused_without_approval(
    exported: BatchLayout, cases: dict[str, Case], config: PilotConfig, tmp_path: Path
) -> None:
    with pytest.raises(judge_manual.ManualJudgeError, match="judge_calls"):
        _import(exported, cases, config, tmp_path, _task(exported))
    assert not (exported.scores / "judge_raw").exists()


@pytest.mark.parametrize(
    ("override", "needle"),
    [
        ({"input_tokens": 0}, "input_tokens"),
        ({"model_identifier": ""}, "unknown"),
        ({"cost_usd": 0.5}, "cost_basis"),
        ({"operator": "unknown"}, "operator"),
        (
            {"isolation": {**ISOLATED, "not_the_development_session": False}},
            "isolation",
        ),
        ({"judge_input_sha256": "0" * 64}, "hash"),
    ],
)
def test_bad_session_metadata_is_refused_and_writes_nothing(
    exported: BatchLayout, cases: dict[str, Case], config: PilotConfig,
    tmp_path: Path, override: dict[str, Any], needle: str,
) -> None:  # fmt: skip
    with pytest.raises(judge_manual.ManualJudgeError, match=needle):
        _import(
            exported, cases, _approved(config), tmp_path, _task(exported), **override
        )
    assert not (exported.scores / "judge_raw").exists()


# --- import outcomes -----------------------------------------------------------


def test_valid_reply_flows_through_the_normal_pipeline(
    exported: BatchLayout, cases: dict[str, Case], config: PilotConfig, tmp_path: Path
) -> None:
    approved = _approved(config)
    task = _task(exported)
    result = _import(exported, cases, approved, tmp_path, task)
    assert result.valid and result.stop_reason is None
    raw = json.loads(
        exported.judge_raw_file(task.doc_id, 1).read_text(encoding="utf-8")
    )
    assert raw["runner"] == "manual-ide-claude-code"
    assert raw["raw_response"].startswith('{"judge_id"')
    assert raw["prompt_version"] and raw["schema_version"]
    assert "input_tokens" in raw["unknown_fields"] and raw["cost_basis"] == "unknown"
    assert raw["session"]["output_tokens"] == "unknown"  # never filled with 0
    parsed = json.loads(exported.judge_file(task.doc_id, 1).read_text(encoding="utf-8"))
    assert parsed["judge_id"] == "manual-ide:claude-opus-5-5" and parsed["output"]
    scores = score_batch(exported, cases, passes=2, pass_threshold=70)
    scored = next(s for s in scores if s.doc_id == task.doc_id)
    assert len(scored.passes) == 1  # pass 2 not imported yet
    assert scored.invalid_passes == [
        {"judge_pass": 2, "problems": ["judge output missing"]}
    ]
    with pytest.raises(ArtifactExistsError):
        _import(exported, cases, approved, tmp_path, task)


def test_invalid_reply_is_recorded_and_stops_the_smoke_test(
    exported: BatchLayout, cases: dict[str, Case], config: PilotConfig, tmp_path: Path
) -> None:
    approved = _approved(config, "smoke")
    task = _task(exported)
    bad = '这是结果：{"judge_id": "x", "total_score": 92}'
    result = _import(exported, cases, approved, tmp_path, task, body=bad)
    assert not result.valid and result.stop_reason == "judge_invalid_output"
    raw = json.loads(
        exported.judge_raw_file(task.doc_id, 1).read_text(encoding="utf-8")
    )
    assert raw["raw_response"] == bad and raw["valid"] is False  # not repaired
    parsed = json.loads(exported.judge_file(task.doc_id, 1).read_text(encoding="utf-8"))
    assert parsed["output"] is None
    with pytest.raises(judge_manual.ManualJudgeError, match="judge_invalid_output"):
        _import(exported, cases, approved, tmp_path, _task(exported, 2))
    assert (
        judge_manual.status(exported, approved)["stop_reason"] == "judge_invalid_output"
    )


def test_model_drift_between_imports_stops(
    exported: BatchLayout, cases: dict[str, Case], config: PilotConfig, tmp_path: Path
) -> None:
    approved = _approved(config, "pilot")
    _import(exported, cases, approved, tmp_path, _task(exported, 1))
    result = _import(exported, cases, approved, tmp_path, _task(exported, 2),
                     model_identifier="claude-sonnet-5-5")  # fmt: skip
    assert result.stop_reason == "model_drift"


def test_unknown_model_is_reported_as_unverifiable(
    exported: BatchLayout, cases: dict[str, Case], config: PilotConfig, tmp_path: Path
) -> None:
    approved = _approved(config, "pilot")
    _import(exported, cases, approved, tmp_path, _task(exported),
            model_identifier="unknown", model_identifier_source="unknown")  # fmt: skip
    state = judge_manual.status(exported, approved)
    assert state["snapshot_verifiability"]["judge"] == "unverifiable_no_model_reported"
    assert state["cost"].startswith("unknown")


def test_report_discloses_manual_judge_and_unknown_cost(
    exported: BatchLayout, cases: dict[str, Case], config: PilotConfig,
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    approved = _approved(config, "pilot")
    for task in judge_manual.load_tasks(exported).values():
        _import(exported, cases, approved, tmp_path, task)
    assert main(["report", "--batch-id", "mj-batch", "--output-root",
                 str(exported.root)]) == 0  # fmt: skip
    report = (exported.reports / "mj-batch.md").read_text(encoding="utf-8")
    assert "人工触发的 IDE Judge" in report and "## 9a." in report
    assert "成本：未知" in report
    capsys.readouterr()


# --- automatic judge auth and run purpose -----------------------------------------


def test_gateway_auth_points_to_the_manual_workflow() -> None:
    no_key = detect_auth({"ANTHROPIC_BASE_URL": "https://gw.example.com"})
    [reason] = judge_auth_blockers(no_key)
    assert "manual IDE judge workflow" in reason and "not read" in reason
    with_key = detect_auth(
        {"ANTHROPIC_BASE_URL": "https://gw.example.com", "ANTHROPIC_API_KEY": "x" * 20}
    )
    assert len(judge_auth_blockers(with_key)) == 2
    assert (
        judge_auth_blockers(with_key, allow_gateway=True, gateway_billing_declared=True)
        == []
    )


def test_smoke_batches_are_labelled_as_not_quality_evidence(
    output_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = str(output_root)
    assert main(["run", "--batch-id", "smk", "--output-root", root,
                 "--cases", "PQB-P07", "--purpose", "smoke"]) == 0  # fmt: skip
    assert main(["judge", "--batch-id", "smk", "--output-root", root]) == 0
    assert main(["report", "--batch-id", "smk", "--output-root", root]) == 0
    report = (Path(root) / "reports" / "smk.md").read_text(encoding="utf-8")
    assert "技术冒烟测试" in report and "不是质量结论" in report
    capsys.readouterr()


def test_real_run_without_purpose_is_refused(
    output_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["run", "--batch-id", "nop", "--output-root", str(output_root),
                 "--mode", "real", "--confirm-spend"])  # fmt: skip
    assert code == 2
    err = capsys.readouterr().err
    assert "--purpose smoke|pilot is required" in err
    assert "real_model_calls is not 'approved'" in err
    assert not output_root.exists()
