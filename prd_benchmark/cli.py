"""Command line entry point: ``python -m prd_benchmark.cli <command>``.

Real model calls and real judge calls are refused unless every approval gate in
``config/pilot.yaml`` is open and ``--confirm-spend`` is passed. In P1 the gates
are closed and no real judge exists, so only ``--mode fake`` and
``--judge mock`` can run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from prd_benchmark._yaml import load_yaml
from prd_benchmark.artifacts import (
    DEFAULT_OUTPUT_ROOT,
    BatchLayout,
    read_json,
    write_json_once,
)
from prd_benchmark.batch import BatchOptions, run_batch
from prd_benchmark.cases import (
    CALIBRATION_BATCH_PREFIX,
    CALIBRATION_CASES_DIR,
    DEFAULT_CASES_DIR,
    PACKAGE_DIR,
    Case,
    freeze_problems,
    load_cases,
)
from prd_benchmark.config import (
    DEFAULT_CONFIG_PATH,
    PilotConfig,
    judge_run_blockers,
    load_config,
)
from prd_benchmark.judge import MockJudge
from prd_benchmark.judge_claude import detect_auth, judge_auth_blockers
from prd_benchmark.pipeline import (
    build_blind_map,
    document_checks,
    load_blind_map,
    run_judging,
    score_batch,
    score_to_dict,
)
from prd_benchmark.pricing import load_snapshot
from prd_benchmark.providers import RealCallsBlockedError
from prd_benchmark.report import write_report

EXIT_BLOCKED = 2


def report_suffix(layout: BatchLayout) -> str:
    """``""`` for the first report, then ``.r2``, ``.r3`` ... (never overwrite).

    Scores are recomputed when human reviews are added, so each recomputation
    gets a new revision instead of replacing the previous one.
    """
    n = 1
    while True:
        suffix = "" if n == 1 else f".r{n}"
        taken = (
            (layout.scores / f"doc_scores{suffix}.json").exists()
            or (layout.reports / f"{layout.batch_id}{suffix}.md").exists()
            or (layout.reports / f"{layout.batch_id}{suffix}.csv").exists()
        )
        if not taken:
            return suffix
        n += 1


def cmd_validate(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    cases = load_cases(args.cases_dir)
    model = config.model.model_id
    print(f"config {config.config_version} ({config.status}); model {model}")
    for case in cases:
        core_r = sum(item.core for item in case.required_items)
        core_c = sum(item.core for item in case.clarifications)
        print(
            f"{case.id} {case.case_version} {case.status:<6} "
            f"H={len(case.hard_constraints)} R={len(case.required_items)} "
            f"(core {core_r}) C={len(case.clarifications)} (core {core_c}) "
            f"X={len(case.critical_defects)}"
        )
    problems = freeze_problems(args.cases_dir)
    print(f"freeze problems: {len(problems)} (real runs stay blocked until 0)")
    for problem in problems:
        print(f"  - {problem}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    options = BatchOptions(
        batch_id=args.batch_id,
        mode=args.mode,
        output_root=args.output_root,
        case_ids=args.cases,
        confirm_spend=args.confirm_spend,
        provider_changelog_date=args.provider_changelog_date,
        purpose=args.purpose,
        config_path=args.config,
        cases_dir=args.cases_dir,
    )
    try:
        summary = asyncio.run(run_batch(options, config))
    except RealCallsBlockedError as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_BLOCKED
    runs = len(summary.runs)
    print(f"batch {summary.batch_id}: {runs} runs, tokens {summary.tokens_used}")
    if summary.aborted:
        print(f"aborted: {summary.aborted}", file=sys.stderr)
        return 1
    return 0


def _claude_version(cli_path: str) -> str | None:
    """``claude --version`` (a local call; no model request, no credentials)."""
    try:
        completed = subprocess.run(
            [cli_path, "--version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    words = completed.stdout.split()
    return words[0] if words else None


def real_judge_blockers(config: PilotConfig, confirm_spend: bool) -> list[str]:
    """Config gates first; the CLI version and auth are inspected only after."""
    preliminary = judge_run_blockers(
        config,
        confirm_spend=confirm_spend,
        auth_blockers=[],
        observed_cli_version=config.judge.claude_code.cli_version,
    )
    if preliminary:
        return preliminary
    auth = detect_auth(os.environ)
    version = _claude_version(config.judge.claude_code.cli_path)
    declared = False
    if config.pricing.judge_snapshot:
        snapshot = load_snapshot(PACKAGE_DIR / config.pricing.judge_snapshot)
        declared = (
            snapshot.billing == "gateway_per_token" and snapshot.status == "verified"
        )
    return judge_run_blockers(
        config,
        confirm_spend=confirm_spend,
        auth_blockers=judge_auth_blockers(
            auth,
            allow_gateway=config.judge.claude_code.allow_gateway,
            gateway_billing_declared=declared,
        ),
        observed_cli_version=version,
    )


def _cases(args: argparse.Namespace) -> dict[str, Case]:
    """Calibration batches (``cal-*``) always use the calibration cases."""
    calibration = args.batch_id.startswith(CALIBRATION_BATCH_PREFIX)
    cases_dir = CALIBRATION_CASES_DIR if calibration else args.cases_dir
    return {case.id: case for case in load_cases(cases_dir)}


def cmd_judge(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.batch_id.startswith(CALIBRATION_BATCH_PREFIX):
        print(
            "refused: calibration batches are judged with judge-manual only, "
            "after both reviewers have locked their scoresheets",
            file=sys.stderr,
        )
        return EXIT_BLOCKED
    if args.judge != "mock":
        blockers = real_judge_blockers(config, args.confirm_spend)
        if blockers:
            print("refused: " + "; ".join(blockers), file=sys.stderr)
            return EXIT_BLOCKED
        return _run_real_judge(args, config)
    layout = BatchLayout(args.output_root, args.batch_id)
    seed = config.execution.condition_order_seed or 0
    if not (layout.scores / "blind_map.json").exists():
        build_blind_map(layout, seed)
    cases = {case.id: case for case in load_cases(args.cases_dir)}
    result = asyncio.run(
        run_judging(
            layout,
            cases,
            MockJudge(),
            passes=config.judge.passes_per_document,
            seed=seed,
        )
    )
    documents = len(load_blind_map(layout))
    print(f"mock judge wrote {result.written} outputs for {documents} documents")
    return 0


def _run_real_judge(args: argparse.Namespace, config: PilotConfig) -> int:
    """Reached only when every gate is open. Not exercised by any test."""
    from prd_benchmark.batch import build_guard, ledger_path
    from prd_benchmark.judge_claude import ClaudeCodeConfig, ClaudeCodeJudge

    layout = BatchLayout(args.output_root, args.batch_id)
    seed = config.execution.condition_order_seed or 0
    if not (layout.scores / "blind_map.json").exists():
        build_blind_map(layout, seed)
    runner = config.judge.claude_code
    judge = ClaudeCodeJudge(
        ClaudeCodeConfig(
            cli_path=runner.cli_path,
            cli_version=runner.cli_version,
            model_id=str(config.judge.model_id),
            effort=runner.effort,
            max_output_tokens=runner.max_output_tokens,
            max_api_requests_per_call=runner.max_api_requests_per_call,
            timeout_seconds=runner.timeout_seconds,
            per_call_soft_budget_usd=runner.per_call_soft_budget_usd,
        ),
        build_guard(config, layout),
        observed_cli_version=runner.cli_version,
    )
    cases = {case.id: case for case in load_cases(args.cases_dir)}
    result = asyncio.run(
        run_judging(
            layout,
            cases,
            judge,
            passes=config.judge.passes_per_document,
            seed=seed,
        )
    )
    write_json_once(ledger_path(layout, "judge"), judge.guard.to_dict())
    print(f"judge wrote {result.written} outputs; stopped: {result.stopped}")
    return 1 if result.stopped else 0


def cmd_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    layout = BatchLayout(args.output_root, args.batch_id)
    cases = _cases(args)
    scores = score_batch(
        layout,
        cases,
        passes=config.judge.passes_per_document,
        pass_threshold=config.scoring.pass_threshold,
    )
    checks = document_checks(layout)
    judge_ids = {
        str(read_json(path)["judge_id"])
        for path in sorted((layout.scores / "judge").glob("*.json"))
    }
    suffix = report_suffix(layout)
    scores_path = layout.scores / f"doc_scores{suffix}.json"
    write_json_once(
        scores_path,
        {
            "rubric_version": config.scoring.rubric_version,
            "checks": checks,
            "documents": [score_to_dict(s) for s in scores],
        },
    )
    markdown_path, csv_path = write_report(
        layout, cases, scores, checks, config, judge_ids, suffix=suffix
    )
    print(f"scores: {scores_path}\nreport: {markdown_path}\ncsv: {csv_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prd_benchmark")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--cases-dir", type=Path, default=DEFAULT_CASES_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="validate config and cases (no calls)")

    run = sub.add_parser("run", help="run conditions A and B for a batch")
    run.add_argument("--batch-id", required=True)
    run.add_argument("--mode", choices=("fake", "real"), default="fake")
    run.add_argument("--cases", nargs="*")
    run.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    run.add_argument("--confirm-spend", action="store_true")
    run.add_argument("--provider-changelog-date")
    run.add_argument("--purpose", choices=("dry_run", "smoke", "pilot"))

    judge = sub.add_parser("judge", help="blind and judge a finished batch")
    judge.add_argument("--batch-id", required=True)
    judge.add_argument("--judge", choices=("mock", "claude"), default="mock")
    judge.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    judge.add_argument("--confirm-spend", action="store_true")

    manual = sub.add_parser("judge-manual", help="manual IDE judge workflow")
    manual_sub = manual.add_subparsers(dest="action", required=True)
    for name in ("export", "status"):
        action = manual_sub.add_parser(name)
        action.add_argument("--batch-id", required=True)
        action.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    session = manual_sub.add_parser("session", help="copy one task to a temp dir")
    session.add_argument("--batch-id", required=True)
    session.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    session.add_argument("--task", required=True)
    imp = manual_sub.add_parser("import", help="import one judge reply")
    imp.add_argument("--batch-id", required=True)
    imp.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    imp.add_argument("--task", required=True)
    imp.add_argument("--response", type=Path, required=True)
    imp.add_argument("--session", type=Path, required=True)

    report = sub.add_parser("report", help="score a judged batch and write a report")
    report.add_argument("--batch-id", required=True)
    report.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)

    cal = sub.add_parser("calibration", help="human calibration (P91, P92), offline")
    cal_sub = cal.add_subparsers(dest="action", required=True)
    for name, extra in (
        ("stage", ()),
        ("export-review", ()),
        ("roles", ("judge-operator", "reviewer-a", "reviewer-b", "adjudicator")),
        ("submit", ("reviewer", "review-id", "sheet")),
        ("disagreements", ("review-id",)),
        ("adjudicate", ("review-id", "adjudicator", "decisions")),
        ("compare", ()),
    ):
        action = cal_sub.add_parser(name)
        action.add_argument("--batch-id", required=True)
        action.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
        for option in extra:
            kind = Path if option in {"sheet", "decisions"} else str
            action.add_argument(f"--{option}", type=kind, required=True)
    return parser


def cmd_calibration(args: argparse.Namespace) -> int:
    """Stage, export, lock, adjudicate, compare. Never calls a model."""
    from prd_benchmark import review

    if not args.batch_id.startswith(CALIBRATION_BATCH_PREFIX):
        print(f"refused: batch id must start with {CALIBRATION_BATCH_PREFIX}",
              file=sys.stderr)  # fmt: skip
        return EXIT_BLOCKED
    config = load_config(args.config)
    layout = BatchLayout(args.output_root, args.batch_id)
    cases = _cases(args)
    if args.action == "stage":
        entries = review.stage_calibration_batch(args.output_root, args.batch_id)
        print(f"staged {len(entries)} calibration documents in {layout.runs}")
    elif args.action == "export-review":
        exported = review.export_review_package(layout, cases)
        leaks = review.package_leaks(layout, exported)
        if leaks:
            print("package leaks: " + "; ".join(leaks), file=sys.stderr)
            return 1
        print(f"exported {len(exported)} documents to {layout.review / 'package'}")
    elif args.action == "roles":
        print(review.assign_roles(
            layout, judge_operator=args.judge_operator, reviewer_a=args.reviewer_a,
            reviewer_b=args.reviewer_b, adjudicator=args.adjudicator,
        ))  # fmt: skip
    elif args.action == "submit":
        print(review.submit_review(layout, args.reviewer, args.review_id, args.sheet))
    elif args.action == "disagreements":
        found = review.disagreements(layout, args.review_id)
        print(json.dumps(found, ensure_ascii=False, indent=2))
    elif args.action == "adjudicate":
        decisions = load_yaml(args.decisions)
        print(review.adjudicate(layout, args.review_id, args.adjudicator, decisions))
    else:
        review.calibration_comparison(
            layout, cases, passes=config.judge.passes_per_document
        )
        print(layout.review / "calibration-comparison.md")
    return 0


def cmd_judge_manual(args: argparse.Namespace) -> int:
    """Offline only: export, prepare a session dir, import, or show status."""
    from prd_benchmark import judge_manual

    config = load_config(args.config)
    layout = BatchLayout(args.output_root, args.batch_id)
    cases = _cases(args)
    if args.action == "export":
        tasks = judge_manual.export_judge_package(
            layout,
            cases,
            passes=config.judge.passes_per_document,
            seed=config.execution.condition_order_seed or 0,
        )
        leaks = judge_manual.package_leaks(layout)
        if leaks:
            print("package leaks condition info: " + "; ".join(leaks), file=sys.stderr)
            return 1
        print(f"exported {len(tasks)} tasks to {judge_manual.workspace(layout)}")
        return 0
    if args.action == "session":
        try:
            print(judge_manual.prepare_session(layout, args.task))
        except judge_manual.ManualJudgeError as error:
            print(f"refused: {error}", file=sys.stderr)
            return EXIT_BLOCKED
        return 0
    if args.action == "status":
        print(
            json.dumps(
                judge_manual.status(layout, config), ensure_ascii=False, indent=2
            )
        )
        return 0
    try:
        result = judge_manual.import_response(
            layout,
            cases,
            config,
            task_id=args.task,
            response_path=args.response,
            session_path=args.session,
        )
    except judge_manual.ManualJudgeError as error:
        print(f"refused: {error}", file=sys.stderr)
        return EXIT_BLOCKED
    print(
        f"imported {result.task_id}: valid={result.valid} error={result.error} "
        f"stop={result.stop_reason}"
    )
    return 1 if result.stop_reason or not result.valid else 0


COMMANDS = {
    "validate": cmd_validate,
    "calibration": cmd_calibration,
    "judge-manual": cmd_judge_manual,
    "run": cmd_run,
    "judge": cmd_judge,
    "report": cmd_report,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
