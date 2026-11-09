"""Blinding, judging, and scoring over a finished batch."""

from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import ValidationError

from prd_benchmark.artifacts import (
    BatchLayout,
    read_json,
    write_json_once,
)
from prd_benchmark.batch import B_DOCUMENT_FILES
from prd_benchmark.cases import Case
from prd_benchmark.checks import check_document
from prd_benchmark.human import load_human_review
from prd_benchmark.judge import (
    Judge,
    JudgeOutput,
    JudgeRequest,
    structural_problems,
)
from prd_benchmark.scoring import DocumentScore, aggregate_document

DOCUMENT_FILES: dict[str, tuple[str, str]] = {
    "A": ("A", "output.md"),
    **{label: ("B", name) for label, name in B_DOCUMENT_FILES.items()},
}


@dataclass
class BlindEntry:
    doc_id: str
    case_id: str
    sha256: str
    labels: list[str] = field(default_factory=list)
    path: str = ""


def collect_documents(layout: BatchLayout) -> list[tuple[str, str, str]]:
    """(case_id, label, relative path) for every document the batch produced."""
    found: list[tuple[str, str, str]] = []
    for case_dir in sorted(p for p in layout.runs.iterdir() if p.is_dir()):
        for label, (condition, name) in DOCUMENT_FILES.items():
            path = case_dir / condition / name
            if path.exists():
                found.append((case_dir.name, label, str(path.relative_to(layout.runs))))
    return found


def build_blind_map(layout: BatchLayout, seed: int) -> list[BlindEntry]:
    """Group identical documents per case and give each group an opaque id.

    The id is derived from the seed, case, and content hash only, so it reveals
    nothing about the condition; the label mapping is written to its own file.
    """
    groups: dict[tuple[str, str], BlindEntry] = {}
    for case_id, label, relative in collect_documents(layout):
        text = (layout.runs / relative).read_text(encoding="utf-8")
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        key = (case_id, sha)
        if key not in groups:
            digest = hashlib.sha256(f"{seed}:{case_id}:{sha}".encode()).hexdigest()
            groups[key] = BlindEntry(f"d-{digest[:10]}", case_id, sha, path=relative)
        groups[key].labels.append(label)
    entries = sorted(groups.values(), key=lambda e: e.doc_id)
    write_json_once(
        layout.scores / "blind_map.json",
        {"seed": seed, "documents": [asdict(e) for e in entries]},
    )
    return entries


def load_blind_map(layout: BatchLayout) -> list[BlindEntry]:
    data = read_json(layout.scores / "blind_map.json")
    return [BlindEntry(**entry) for entry in data["documents"]]


def item_order(case: Case, judge_pass: int, doc_id: str, seed: int) -> list[str]:
    order = [item.id for item in case.required_items] + [
        item.id for item in case.clarifications
    ]
    if judge_pass > 1:
        random.Random(f"{seed}:{doc_id}:{judge_pass}").shuffle(order)
    return order


@dataclass
class JudgingResult:
    written: int = 0
    stopped: str | None = None


async def run_judging(
    layout: BatchLayout,
    cases: dict[str, Case],
    judge: Judge,
    *,
    passes: int,
    seed: int,
) -> JudgingResult:
    """Judge every blinded document ``passes`` times, one fresh call each.

    A judge with an ``attempt`` method (the real CLI judge) also yields its raw
    reply, saved to ``judge_raw/`` separately from the parsed record. Invalid
    output is recorded, never retried. A stop condition ends judging at once;
    everything written so far is kept.
    """
    result = JudgingResult()
    attempt_fn = getattr(judge, "attempt", None)
    for entry in load_blind_map(layout):
        case = cases[entry.case_id]
        document = (layout.runs / entry.path).read_text(encoding="utf-8")
        for judge_pass in range(1, passes + 1):
            if layout.judge_file(entry.doc_id, judge_pass).exists():
                continue  # write-once: an earlier command already judged it
            order = item_order(case, judge_pass, entry.doc_id, seed)
            request = JudgeRequest(
                entry.doc_id, case, document, judge_pass, tuple(order)
            )
            record: dict[str, Any] = {
                "doc_id": entry.doc_id,
                "judge_pass": judge_pass,
                "judge_id": judge.judge_id,
                "item_order": order,
                "output": None,
                "structural_problems": [],
                "parse_error": None,
            }
            output: JudgeOutput | None = None
            stop: str | None = None
            if attempt_fn is not None:
                attempt = await attempt_fn(request)
                if attempt.raw.get("refused_before_call"):
                    result.stopped = attempt.stop_reason
                    return result
                write_json_once(
                    layout.judge_raw_file(entry.doc_id, judge_pass), attempt.raw
                )
                output, stop = attempt.output, attempt.stop_reason
                if output is None:
                    record["parse_error"] = attempt.error
            else:
                try:
                    output = await judge.evaluate(request)
                    output = JudgeOutput.model_validate(output.model_dump())
                except ValidationError as error:
                    record["parse_error"] = str(error)[:2000]
            if output is not None:
                record["output"] = output.model_dump(mode="json")
                record["structural_problems"] = structural_problems(output, case)
            write_json_once(layout.judge_file(entry.doc_id, judge_pass), record)
            result.written += 1
            if stop is not None:
                result.stopped = stop
                return result
    return result


def score_batch(
    layout: BatchLayout,
    cases: dict[str, Case],
    *,
    passes: int,
    pass_threshold: float,
) -> list[DocumentScore]:
    scores: list[DocumentScore] = []
    for entry in load_blind_map(layout):
        case = cases[entry.case_id]
        document = (layout.runs / entry.path).read_text(encoding="utf-8")
        outputs: list[tuple[int, JudgeOutput | None, list[str]]] = []
        for judge_pass in range(1, passes + 1):
            path = layout.judge_file(entry.doc_id, judge_pass)
            if not path.exists():
                outputs.append((judge_pass, None, ["judge output missing"]))
                continue
            record = read_json(path)
            raw = record.get("output")
            parsed = JudgeOutput.model_validate(raw) if raw is not None else None
            problems = list(record.get("structural_problems") or [])
            if record.get("parse_error"):
                problems.append("judge output failed schema validation")
            outputs.append((judge_pass, parsed, problems))
        human = load_human_review(layout.human_file(entry.doc_id))
        if human is not None and human.doc_id != entry.doc_id:
            raise ValueError(f"human review for {human.doc_id} filed as {entry.doc_id}")
        scores.append(
            aggregate_document(
                doc_id=entry.doc_id,
                case=case,
                labels=entry.labels,
                document=document,
                outputs=outputs,
                human=human,
                pass_threshold=pass_threshold,
            )
        )
    return scores


def document_checks(layout: BatchLayout) -> dict[str, dict[str, Any]]:
    checks: dict[str, dict[str, Any]] = {}
    for entry in load_blind_map(layout):
        text = (layout.runs / entry.path).read_text(encoding="utf-8")
        checks[entry.doc_id] = check_document(text).to_dict()
    return checks


def score_to_dict(score: DocumentScore) -> dict[str, Any]:
    """Serialised score. ``final_total`` is null while a claim is pending."""
    return {
        "doc_id": score.doc_id,
        "case_id": score.case_id,
        "labels": score.labels,
        "provenance": score.provenance,
        "status": score.status,
        "final_total": score.final_total,
        "scenarios": score.scenarios,
        "candidate_effects": score.candidate_effects,
        "passes": [
            {
                "judge_pass": p.judge_pass,
                "counts": p.counts,
                "judgments": [asdict(j) for j in p.judgments],
                "claims": [asdict(c) for c in p.claims],
                "invalid_claims": p.invalid_claims,
            }
            for p in score.passes
        ],
        "invalid_passes": score.invalid_passes,
        "candidates": [asdict(c) for c in score.candidates],
        "unknown_decisions": score.unknown_decisions,
        "disagreements": score.disagreements,
        "pass_status": score.pass_status,
        "provisional_pass": score.provisional_pass,
    }
