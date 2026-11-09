"""Run one batch: every selected case under conditions A and B."""

from __future__ import annotations

import hashlib
import random
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from prd_benchmark.artifacts import (
    BatchLayout,
    write_json_once,
    write_jsonl_once,
    write_text_once,
)
from prd_benchmark.cases import (
    CALIBRATION_BATCH_PREFIX,
    CALIBRATION_CASES_DIR,
    DEFAULT_CASES_DIR,
    Case,
    file_sha256,
    freeze_problems,
    load_cases,
    load_manifest,
)
from prd_benchmark.config import DEFAULT_CONFIG_PATH, PilotConfig, real_run_blockers
from prd_benchmark.fake_openai import FakeBehavior, FakeOpenAIClient
from prd_benchmark.guard import CallGuard, SpendLedger, StopMonitor, load_prior
from prd_benchmark.pricing import load_snapshot
from prd_benchmark.providers import (
    RealCallsBlockedError,
    build_provider,
    build_real_client,
)
from prd_benchmark.recording import CallContext, RecordingClient, TokenBudget
from prd_benchmark.run_single import run_condition_a
from prd_benchmark.run_workflow import run_condition_b

#: Configuration errors: the batch stops instead of burning budget on every case.
ABORT_CODES = frozenset(
    {
        "PROVIDER_MODEL_INVALID",
        "PROVIDER_AUTHENTICATION_FAILED",
        "PROVIDER_INSUFFICIENT_BALANCE",
        "PROVIDER_FORBIDDEN",
    }
)

B_DOCUMENT_FILES = {"B.best": "best.md", "B.last": "last.md", "B.v1": "v1.md"}


@dataclass
class BatchOptions:
    batch_id: str
    mode: Literal["fake", "real"]
    output_root: Path
    case_ids: list[str] | None = None
    confirm_spend: bool = False
    provider_changelog_date: str | None = None
    fake_behavior: FakeBehavior | None = None
    #: Tests inject a guard to exercise budgets and stop conditions offline.
    guard: CallGuard | None = None
    #: ``smoke`` batches are technical checks, never quality evidence.
    purpose: Literal["dry_run", "smoke", "pilot"] | None = None
    config_path: Path = DEFAULT_CONFIG_PATH
    cases_dir: Path = DEFAULT_CASES_DIR


@dataclass
class BatchSummary:
    batch_id: str
    mode: str
    runs: list[dict[str, Any]] = field(default_factory=list)
    aborted: str | None = None
    tokens_used: int = 0
    stop_reason: str | None = None


def _git(*args: str) -> str | None:
    """Read-only git query; ``None`` when git is unavailable."""
    try:
        completed = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout


def git_state() -> dict[str, Any]:
    commit = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    dirty = (
        [line[3:] for line in status.splitlines() if line.strip()]
        if status is not None
        else None
    )
    return {"commit": commit.strip() if commit else None, "dirty_paths": dirty}


def condition_orders(cases: list[Case], seed: int) -> dict[str, list[str]]:
    rng = random.Random(seed)
    orders: dict[str, list[str]] = {}
    for case in cases:
        order = ["A", "B"]
        rng.shuffle(order)
        orders[case.id] = order
    return orders


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def select_cases(cases: list[Case], case_ids: list[str] | None) -> list[Case]:
    if not case_ids:
        return cases
    known = {case.id: case for case in cases}
    missing = [case_id for case_id in case_ids if case_id not in known]
    if missing:
        raise ValueError(f"unknown case ids: {missing}")
    return [known[case_id] for case_id in sorted(case_ids)]


def ledger_path(layout: BatchLayout, channel: str) -> Path:
    """Next free ledger file; each command of a batch writes its own."""
    folder = layout.root / "ledgers" / layout.batch_id
    n = 1
    while (folder / f"{channel}-{n:03d}.json").exists():
        n += 1
    return folder / f"{channel}-{n:03d}.json"


def build_guard(
    config: PilotConfig, layout: BatchLayout, *, judge_mode: str | None = None
) -> CallGuard:
    """The batch-wide guard: caps from config, priors from earlier ledgers."""
    from prd_benchmark.cases import PACKAGE_DIR

    pricing = config.pricing
    prices = {
        "generator": load_snapshot(PACKAGE_DIR / pricing.generator_snapshot)
        if pricing.generator_snapshot
        else None,
        "judge": load_snapshot(PACKAGE_DIR / pricing.judge_snapshot)
        if pricing.judge_snapshot
        else None,
    }
    existing = sorted((layout.root / "ledgers" / layout.batch_id).glob("*.json"))
    tokens, usd, by_channel = load_prior(existing)
    ledger = SpendLedger(
        token_limit=config.approvals.token_budget_limit,
        usd_limit=config.approvals.usd_budget_limit,
        prior_tokens=tokens,
        prior_usd=usd,
        prior_by_channel=by_channel,
    )
    monitor = StopMonitor(
        judge_mode=judge_mode or config.judge.stop_mode,  # type: ignore[arg-type]
        configured_models={
            "generator": config.model.model_id,
            "judge": config.judge.model_id,
        },
    )
    return CallGuard(ledger, monitor, prices, estimator=pricing.input_token_estimator)


async def run_batch(options: BatchOptions, config: PilotConfig) -> BatchSummary:
    layout = BatchLayout(options.output_root, options.batch_id)
    cases = select_cases(load_cases(options.cases_dir), options.case_ids)
    calibration_ids = {e.id for e in load_manifest(CALIBRATION_CASES_DIR).cases}
    if options.batch_id.startswith(CALIBRATION_BATCH_PREFIX) or any(
        case.id in calibration_ids for case in cases
    ):
        # Calibration documents are fixed files, never generated, and never
        # share a batch (or a batch-id namespace) with Pilot runs.
        raise ValueError("calibration cases and cal-* batch ids are not run here")
    real = options.mode == "real"
    if real:
        blockers = real_run_blockers(
            config,
            confirm_spend=options.confirm_spend,
            case_freeze_problems=freeze_problems(
                options.cases_dir, options.case_ids or None, config
            ),
            provider_changelog_date=options.provider_changelog_date,
        )
        if options.purpose not in ("smoke", "pilot"):
            blockers.append("--purpose smoke|pilot is required for real runs")
        if blockers:
            # Raised before anything is written or any client is built.
            raise RealCallsBlockedError("; ".join(blockers))
    if layout.runs.exists():
        raise FileExistsError(f"batch {options.batch_id} already exists")
    seed = config.execution.condition_order_seed
    seed = 0 if seed is None else seed
    orders = condition_orders(cases, seed)
    budget = TokenBudget(None)  # superseded by the guard; kept for the record
    guard = options.guard or (build_guard(config, layout) if real else None)
    real_client = build_real_client(config.model, blockers=[]) if real else None
    manifest = load_manifest(options.cases_dir)
    case_files = {entry.id: entry.file for entry in manifest.cases}
    summary = BatchSummary(batch_id=options.batch_id, mode=options.mode)
    started_at = datetime.now(UTC).isoformat()

    for case in cases:
        if summary.aborted:
            break
        request = case.frozen_input.to_request()
        case_sha = file_sha256(options.cases_dir / case_files[case.id])
        for condition in orders[case.id]:
            inner = (
                real_client
                if real_client is not None
                else FakeOpenAIClient(options.fake_behavior)
            )
            recorder = RecordingClient(
                inner,
                context=CallContext(options.batch_id, case.id, condition),
                budget=budget,
                guard=guard,
            )
            provider = build_provider(recorder, config.model)
            run_dir = layout.run_dir(case.id, condition)
            input_record = {
                "case_id": case.id,
                "case_version": case.case_version,
                "case_sha256": case_sha,
                "condition": condition,
                "request": request.model_dump(mode="json"),
            }
            meta: dict[str, Any] = {"case_id": case.id, "condition": condition}
            try:
                if condition == "A":
                    single = await run_condition_a(
                        request,
                        provider,
                        max_attempts=config.conditions.A.max_attempts,
                        attempt_timeout_seconds=config.conditions.A.attempt_timeout_seconds,
                    )
                    input_record["output_language"] = single.output_language
                    meta.update(single.to_dict())
                    meta.pop("content")
                    if single.content is not None:
                        write_text_once(run_dir / "output.md", single.content)
                        meta["documents"] = {"A": _sha(single.content)}
                    error = single.error_code
                else:
                    result = await run_condition_b(
                        request,
                        provider,
                        model=config.model,
                        condition=config.conditions.B,
                    )
                    input_record["output_language"] = result.snapshot.output_language
                    meta.update(result.meta())
                    documents = result.documents()
                    for label, text in documents.items():
                        write_text_once(run_dir / B_DOCUMENT_FILES[label], text)
                    meta["documents"] = {k: _sha(v) for k, v in documents.items()}
                    write_json_once(
                        run_dir / "snapshot.json",
                        result.snapshot.model_dump(mode="json"),
                    )
                    error = result.error_code
            except Exception as exc:
                meta["status"] = "harness_error"
                meta["error_code"] = f"HARNESS_ERROR:{type(exc).__name__}"
                error = meta["error_code"]
                summary.aborted = f"harness error in {case.id}/{condition}"
            finally:
                write_json_once(run_dir / "input.json", input_record)
                write_jsonl_once(run_dir / "calls.jsonl", recorder.records_as_dicts())
            meta["call_count"] = len(recorder.records)
            write_json_once(run_dir / "meta.json", meta)
            summary.runs.append(meta)
            if error in ABORT_CODES:
                summary.aborted = f"{error} in {case.id}/{condition}"
            if guard is not None and guard.monitor.stop_reason is not None:
                summary.stop_reason = guard.monitor.stop_reason
                summary.aborted = summary.aborted or (
                    f"stop condition {guard.monitor.stop_reason}: "
                    f"{guard.monitor.stop_detail}"
                )
            if summary.aborted:
                break

    summary.tokens_used = guard.ledger.charged_tokens if guard else budget.used
    if guard is not None:
        write_json_once(ledger_path(layout, "generator"), guard.to_dict())
    write_json_once(
        layout.runs / "batch.json",
        {
            "batch_id": options.batch_id,
            "mode": options.mode,
            "purpose": options.purpose
            or ("dry_run" if options.mode == "fake" else "unspecified"),
            "started_at": started_at,
            "ended_at": datetime.now(UTC).isoformat(),
            "git": git_state(),
            "config_sha256": file_sha256(options.config_path),
            "config_version": config.config_version,
            "model": config.model.model_dump(mode="json"),
            "case_set_version": manifest.case_set_version,
            "case_set_status": manifest.status,
            "condition_order_seed": seed,
            "condition_orders": orders,
            "provider_changelog_date": options.provider_changelog_date,
            "budget": guard.ledger.summary() if guard else None,
            "stop": guard.monitor.to_dict() if guard else None,
            "aborted": summary.aborted,
            "case_ids": [case.id for case in cases],
        },
    )
    return summary
