"""Offline end-to-end drill of the manual IDE judge on P07.

export -> session -> import -> parse -> quote check -> score -> dedupe ->
human decision -> report, with fixed replies standing in for the IDE session.
No model is called; the approved config exists only in memory.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest

from prd_benchmark import judge_manual
from prd_benchmark._yaml import dump_yaml
from prd_benchmark.artifacts import ArtifactExistsError, BatchLayout
from prd_benchmark.cases import Case
from prd_benchmark.cli import main
from prd_benchmark.config import PilotConfig
from prd_benchmark.judge import DIMENSIONS
from prd_benchmark.pipeline import load_blind_map, score_batch, score_to_dict
from prd_benchmark.scoring import hard_candidate_id
from prd_benchmark.tests.test_judge_manual import ISOLATED, _approved

BAD_QUOTE = "本系统支持一键导出全部候选人简历并自动发送给外部猎头"


@pytest.fixture
def drill(output_root: Path, cases: dict[str, Case]) -> BatchLayout:
    assert main(["run", "--batch-id", "drill", "--output-root", str(output_root),
                 "--cases", "PQB-P07", "--purpose", "smoke"]) == 0  # fmt: skip
    layout = BatchLayout(output_root, "drill")
    judge_manual.export_judge_package(
        layout,
        cases,
        passes=2,
        seed=0,
        rng=random.Random(5),  # type: ignore[arg-type]
    )
    return layout


def _lines(document: str) -> list[str]:
    return [line.strip() for line in document.splitlines() if len(line.strip()) > 12]


def _reply(case: Case, document: str, judge_pass: int) -> str:
    """Pass 1 and pass 2 raise the same H6 claim (one candidate after dedupe);
    pass 2 also cites one quote that is not in the document."""
    lines = _lines(document)
    quote, claim_quote = lines[0][:40], lines[1][:40]

    def item(item_id: str) -> dict[str, Any]:
        return {"item_id": item_id, "verdict": "covered", "evidence_quotes": [quote],
                "rationale": "文档写明了该规则"}  # fmt: skip

    items = [item(r.id) for r in case.required_items]
    items[0]["hard_constraint_claim"] = {
        "violated_constraint": "H6",
        "quotes": [claim_quote],
        "behavior_impact": f"「{claim_quote}」意味着导出不经过 HR 主管审批即可完成",
        "defect_key": "export-without-approval",
    }
    if judge_pass == 2:
        items[1]["evidence_quotes"] = [BAD_QUOTE]
    return json.dumps(
        {
            "judge_id": "ide",
            "items": items,
            "clarifications": [item(c.id) for c in case.clarifications],
            "dimensions": [{"dimension": d, "anchor": 4} for d in DIMENSIONS],
        },
        ensure_ascii=False,
    )


def _session_file(folder: Path, task: judge_manual.JudgeTask, **extra: Any) -> Path:
    data = {
        "task_id": task.task_id,
        "judge_input_sha256": task.judge_input_sha256,
        "operator": "judge-operator-tbd",
        "model_identifier": "claude-opus-5-5",
        "model_identifier_source": "IDE model picker",
        "isolation": ISOLATED,
        **extra,
    }
    path = folder / "session.yaml"
    path.write_text(dump_yaml(data), encoding="utf-8")
    return path


def _document(layout: BatchLayout, doc_id: str) -> str:
    entry = next(e for e in load_blind_map(layout) if e.doc_id == doc_id)
    return (layout.runs / entry.path).read_text(encoding="utf-8")


def _human(layout: BatchLayout, doc_id: str, decision: str, candidate: str) -> None:
    path = layout.human_file(doc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        dump_yaml(
            {
                "doc_id": doc_id,
                "reviewer": "adjudicator-tbd",
                "scope": "partial",
                "critical_decisions": [
                    {"candidate_id": candidate, "decision": decision}
                ],
            }
        ),
        encoding="utf-8",
    )


def test_p07_manual_judge_end_to_end(
    drill: BatchLayout, cases: dict[str, Case], config: PilotConfig,
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    approved = _approved(config, "smoke")
    tasks = judge_manual.load_tasks(drill)
    docs = load_blind_map(drill)
    # Export: no leaks, unique task ids and input hashes, two passes per doc.
    assert judge_manual.package_leaks(drill) == []
    assert len(tasks) == 2 * len(docs)
    assert len({t.judge_input_sha256 for t in tasks.values()}) == len(tasks)
    assert {(t.doc_id, t.judge_pass) for t in tasks.values()} == {
        (d.doc_id, n) for d in docs for n in (1, 2)
    }
    # Session: every task gets its own new directory outside the repository.
    sessions = {
        t.task_id: judge_manual.prepare_session(drill, t.task_id, parent=tmp_path)
        for t in tasks.values()
    }
    assert len(set(sessions.values())) == len(tasks)
    for folder in sessions.values():
        assert not folder.is_relative_to(judge_manual.REPO_ROOT)
    # Import every reply as the operator would, from the session directory.
    for task in sorted(tasks.values(), key=lambda t: t.task_id):
        folder = sessions[task.task_id]
        reply = _reply(cases["PQB-P07"], _document(drill, task.doc_id), task.judge_pass)
        (folder / "response.json").write_text(reply, encoding="utf-8")
        result = judge_manual.import_response(
            drill, cases, approved, task_id=task.task_id,
            response_path=folder / "response.json",
            session_path=_session_file(folder, task),
        )  # fmt: skip
        assert result.valid and result.stop_reason is None
    # Raw and parsed records are separate files with separate content.
    for task in tasks.values():
        raw = json.loads(drill.judge_raw_file(task.doc_id, task.judge_pass).read_text())
        parsed = json.loads(drill.judge_file(task.doc_id, task.judge_pass).read_text())
        assert "raw_response" in raw and "raw_response" not in parsed
        assert "output" in parsed and "output" not in raw
        assert raw["session"]["cost_usd"] == "unknown"
        assert raw["session"]["input_tokens"] == "unknown"
    # Score: the bad quote is unverified, the claim is one pending candidate.
    candidate = hard_candidate_id("H6", "export-without-approval")
    for score in score_batch(drill, cases, passes=2, pass_threshold=70):
        data = score_to_dict(score)
        pass2 = next(p for p in data["passes"] if p["judge_pass"] == 2)
        assert pass2["counts"]["unverified_judgments"] == 1
        [claim] = [c for c in data["candidates"] if c["rule_id"] == "G1"]
        assert claim["candidate_id"] == candidate and claim["decision"] == "pending"
        assert sorted(claim["occurrences"]) == ["pass1:R1", "pass2:R1"]
        assert "same_h_and_defect_key" in claim["merge_basis"]
        assert data["final_total"] is None and data["pass_status"] == "pending"
        assert data["provisional_pass"] is None
    # Human decisions update the result.
    doc_id = docs[0].doc_id
    _human(drill, doc_id, "confirmed", candidate)
    confirmed = next(
        s for s in score_batch(drill, cases, passes=2, pass_threshold=70)
        if s.doc_id == doc_id
    )  # fmt: skip
    assert confirmed.final_total is not None and confirmed.pass_status == "fail"
    _human(drill, doc_id, "rejected", candidate)
    rejected = next(
        s for s in score_batch(drill, cases, passes=2, pass_threshold=70)
        if s.doc_id == doc_id
    )  # fmt: skip
    assert rejected.final_total is not None
    assert rejected.final_total > confirmed.final_total
    assert rejected.pass_status != "pending"
    # Report: smoke banner, manual judge disclosed, cost unknown -- never 0.
    assert main(["report", "--batch-id", "drill", "--output-root",
                 str(drill.root)]) == 0  # fmt: skip
    report = (drill.reports / "drill.md").read_text(encoding="utf-8")
    assert "技术冒烟测试" in report and "人工触发的 IDE Judge" in report
    assert "成本：未知" in report and "待定" in report
    manual = report.split("## 9a.")[1].split("\n## ")[0]
    assert "US$0" not in manual and "cost_usd" in manual
    # The manual judge never enters the budget ledger, so it is never counted
    # as zero spend inside the caps either.
    assert not (drill.root / "ledgers").exists()
    # A repeated import is refused and writes nothing new.
    task = next(iter(tasks.values()))
    folder = sessions[task.task_id]
    with pytest.raises(ArtifactExistsError):
        judge_manual.import_response(
            drill, cases, approved, task_id=task.task_id,
            response_path=folder / "response.json",
            session_path=folder / "session.yaml",
        )  # fmt: skip
    capsys.readouterr()


@pytest.mark.parametrize(
    ("body", "session", "outcome"),
    [
        ("{not json", {}, "invalid"),
        ('```json\n{"judge_id": "x"}\n```', {}, "invalid"),
        (None, {"operator": "unknown"}, "refused"),
        (None, {"isolation": {**ISOLATED, "one_task_per_session": False}}, "refused"),
        (None, {"output_tokens": 0}, "refused"),
        (None, {"cost_usd": 0.0}, "refused"),
    ],
)
def test_bad_replies_and_metadata(
    drill: BatchLayout, cases: dict[str, Case], config: PilotConfig,
    tmp_path: Path, body: str | None, session: dict[str, Any], outcome: str,
) -> None:  # fmt: skip
    approved = _approved(config, "smoke")
    task = sorted(judge_manual.load_tasks(drill).values(), key=lambda t: t.task_id)[0]
    folder = judge_manual.prepare_session(drill, task.task_id, parent=tmp_path)
    reply = body or _reply(cases["PQB-P07"], _document(drill, task.doc_id), 1)
    (folder / "response.json").write_text(reply, encoding="utf-8")
    kwargs = {
        "task_id": task.task_id,
        "response_path": folder / "response.json",
        "session_path": _session_file(folder, task, **session),
    }
    if outcome == "refused":
        with pytest.raises(judge_manual.ManualJudgeError):
            judge_manual.import_response(drill, cases, approved, **kwargs)  # type: ignore[arg-type]
        assert not (drill.scores / "judge_raw").exists()
        return
    result = judge_manual.import_response(drill, cases, approved, **kwargs)  # type: ignore[arg-type]
    assert not result.valid and result.stop_reason == "judge_invalid_output"
    raw = json.loads(drill.judge_raw_file(task.doc_id, task.judge_pass).read_text())
    assert raw["raw_response"] == reply  # stored as received, never repaired
    assert judge_manual.status(drill, approved)["stop_reason"] == "judge_invalid_output"


def test_real_calls_stay_refused(
    drill: BatchLayout, cases: dict[str, Case], config: PilotConfig, tmp_path: Path,
    output_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    # Manual import without judge approval: refused, nothing written.
    task = next(iter(judge_manual.load_tasks(drill).values()))
    folder = judge_manual.prepare_session(drill, task.task_id, parent=tmp_path)
    (folder / "response.json").write_text("{}", encoding="utf-8")
    with pytest.raises(judge_manual.ManualJudgeError, match="judge_calls"):
        judge_manual.import_response(
            drill, cases, config, task_id=task.task_id,
            response_path=folder / "response.json",
            session_path=_session_file(folder, task),
        )  # fmt: skip
    assert not (drill.scores / "judge_raw").exists()
    # Real DeepSeek generation for P07 alone: refused before anything is written.
    code = main(["run", "--batch-id", "p07-real", "--output-root", str(output_root),
                 "--mode", "real", "--cases", "PQB-P07", "--purpose", "smoke",
                 "--confirm-spend"])  # fmt: skip
    err = capsys.readouterr().err
    assert code == 2 and "real_model_calls is not 'approved'" in err
    assert "confirmed_by" in err  # the P07 freeze still needs a human sign-off
    assert not (output_root / "runs" / "p07-real").exists()
    # Automatic Claude judge: refused.
    assert main(["judge", "--batch-id", "drill", "--output-root", str(output_root),
                 "--judge", "claude", "--confirm-spend"]) == 2  # fmt: skip
    capsys.readouterr()
