from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from prd_benchmark.cases import PACKAGE_DIR
from prd_benchmark.config import PilotConfig, budget_blockers
from prd_benchmark.fake_openai import FakeBehavior, FakeOpenAIClient
from prd_benchmark.guard import (
    BudgetAccountingError,
    BudgetExceededError,
    CallGuard,
    SpendLedger,
    StopBatchError,
    StopMonitor,
    input_token_upper_bound,
    load_prior,
)
from prd_benchmark.pricing import UsageBreakdown, estimate_usd, load_snapshot
from prd_benchmark.providers import build_provider
from prd_benchmark.recording import CallContext, RecordingClient
from prd_benchmark.run_single import run_condition_a
from prd_benchmark.tests.helpers import status_error

DEEPSEEK = load_snapshot(PACKAGE_DIR / "price_snapshots/2026-10-27-deepseek-flash.yaml")
OPUS = load_snapshot(PACKAGE_DIR / "price_snapshots/2026-10-27-claude-opus-5-5.yaml")


def _guard(
    tokens: int | None = None, usd: float | None = None, **monitor: object
) -> CallGuard:
    return CallGuard(
        SpendLedger(token_limit=tokens, usd_limit=usd),
        StopMonitor(**monitor),  # type: ignore[arg-type]
        {"generator": DEEPSEEK, "judge": OPUS},
    )


# --- price snapshots ---------------------------------------------------------


def test_snapshots_are_drafts_until_a_person_verifies_them() -> None:
    for snapshot in (DEEPSEEK, OPUS):
        assert snapshot.status == "draft" and snapshot.verified_by is None
        assert snapshot.source_url.startswith("https://")


def test_peak_window_pricing() -> None:
    tuesday_peak = datetime(2026, 10, 27, 2, 30, tzinfo=UTC)
    tuesday_off = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
    saturday = datetime(2026, 10, 31, 2, 30, tzinfo=UTC)
    assert DEEPSEEK.price("output", tuesday_peak) == 1.2
    assert DEEPSEEK.price("output", tuesday_off) == 0.6
    assert DEEPSEEK.price("output", saturday) == 0.6
    assert DEEPSEEK.price("output", None) == 1.2  # unknown time: higher price
    assert DEEPSEEK.worst_input_usd_per_mtok == 0.3


def test_estimate_requires_complete_usage() -> None:
    assert estimate_usd(OPUS, UsageBreakdown(output=10), None) is None
    usage = UsageBreakdown(
        input_cache_miss=1_000_000, input_cache_hit=1_000_000,
        cache_write=1_000_000, output=1_000_000,
    )  # fmt: skip
    # 4 + 0.20 + 8 (cache write at the higher 1h rate) + 20
    assert estimate_usd(OPUS, usage, None) == pytest.approx(32.2)


def test_input_bound_is_conservative_for_cjk() -> None:
    assert input_token_upper_bound("需求文档") == 12
    assert input_token_upper_bound("需求文档", "chars") == 4


# --- reservation before the call ---------------------------------------------


def test_reservation_blocks_a_call_that_could_exceed_either_cap() -> None:
    by_tokens = _guard(tokens=1_000)
    with pytest.raises(BudgetExceededError) as error:
        by_tokens.before_call("generator", "g", "x" * 100, 1_000)
    assert error.value.reason == "token_budget"
    by_cost = _guard(usd=0.01)
    # 100 input bytes + 16000 output at the worst DeepSeek output price 1.2/M
    with pytest.raises(BudgetExceededError) as error:
        by_cost.before_call("generator", "g", "x" * 100, 16_000)
    assert error.value.reason == "cost_budget"
    assert by_cost.monitor.stop_reason == "cost_budget"
    # Latched: even a tiny call is refused afterwards.
    with pytest.raises(StopBatchError):
        by_cost.before_call("generator", "g", "x", 1)


def test_settled_usage_releases_only_the_unused_part() -> None:
    guard = _guard(tokens=50_000, usd=5.0)
    reservation = guard.before_call("generator", "g", "x" * 1_000, 16_000)
    assert guard.ledger.charged_tokens == 17_000
    guard.after_call(
        reservation,
        usage=UsageBreakdown(input_cache_miss=300, input_cache_hit=0, output=2_000),
        at=None,
        timed_out=False,
        models=["deepseek-flash"],
    )
    assert guard.ledger.charged_tokens == 2_300
    assert reservation.status == "settled"


@pytest.mark.parametrize(
    "usage",
    [None, UsageBreakdown(), UsageBreakdown(input_cache_miss=10)],
)
def test_unknown_usage_keeps_the_worst_case_charged(
    usage: UsageBreakdown | None,
) -> None:
    guard = _guard(tokens=100_000, usd=5.0)
    reservation = guard.before_call("judge", "j", "x" * 1_000, 32_000)
    reserved = (reservation.reserved_tokens, reservation.reserved_usd)
    guard.after_call(reservation, usage=usage, at=None, timed_out=False)
    assert reservation.status == "held_unknown"
    assert (guard.ledger.charged_tokens, guard.ledger.charged_usd) == reserved
    summary = guard.ledger.summary()
    assert summary["by_channel"]["judge"]["held_unknown_usd"] == reserved[1]
    assert summary["cost_basis"] == "estimate_from_price_snapshot"


def test_double_settlement_is_an_accounting_error() -> None:
    guard = _guard(tokens=100_000)
    reservation = guard.before_call("generator", "g", "x", 10)
    guard.after_call(reservation, usage=None, at=None, timed_out=False)
    with pytest.raises(BudgetAccountingError):
        guard.after_call(reservation, usage=None, at=None, timed_out=False)
    assert guard.monitor.stop_reason == "accounting"


def test_cost_cap_without_a_price_snapshot_refuses() -> None:
    guard = CallGuard(SpendLedger(None, 5.0), StopMonitor(), {"judge": None})
    with pytest.raises(BudgetAccountingError):
        guard.before_call("judge", "j", "x", 10)


def test_request_multiplier_scales_the_reservation() -> None:
    guard = _guard(tokens=10_000_000)
    one = guard.before_call("judge", "a", "x" * 100, 1_000)
    three = guard.before_call("judge", "b", "x" * 100, 1_000, requests=3)
    assert three.reserved_tokens == 3 * one.reserved_tokens
    assert three.reserved_usd == pytest.approx(3 * one.reserved_usd)


def test_reaching_a_cap_after_a_call_stops_the_next_one() -> None:
    guard = _guard(tokens=10_000)
    reservation = guard.before_call("generator", "g", "x", 9_000)
    with pytest.raises(BudgetExceededError):
        guard.after_call(
            reservation,
            usage=UsageBreakdown(input_cache_miss=1, output=9_999),
            at=None,
            timed_out=False,
        )
    with pytest.raises(StopBatchError):
        guard.before_call("generator", "g", "x", 1)


def test_prior_ledgers_count_toward_the_caps(tmp_path: Path) -> None:
    guard = _guard(tokens=1_000_000, usd=5.0)
    held = guard.before_call("generator", "g", "x" * 10, 16_000)
    guard.after_call(held, usage=None, at=None, timed_out=False)
    path = tmp_path / "generator-001.json"
    path.write_text(json.dumps(guard.ledger.to_dict()), encoding="utf-8")
    tokens, usd, by_channel = load_prior([path])
    assert tokens == held.reserved_tokens and usd == held.reserved_usd
    assert by_channel["generator"]["held_unknown_usd"] == held.reserved_usd


# --- stop conditions ---------------------------------------------------------


def test_model_drift_stops_the_batch() -> None:
    monitor = StopMonitor()
    monitor.observe_model("generator", ["deepseek-flash"])
    with pytest.raises(StopBatchError) as error:
        monitor.observe_model("generator", ["deepseek-flash-1101"])
    assert error.value.reason == "model_drift"


def test_alias_only_or_missing_model_is_unverifiable_not_drift_free() -> None:
    monitor = StopMonitor(configured_models={"generator": "deepseek-flash"})
    monitor.observe_model("generator", ["deepseek-flash"])
    monitor.observe_model("judge", [])
    verdict = monitor.snapshot_verifiability()
    assert verdict["generator"] == "unverifiable_alias_only"
    assert verdict["judge"] == "unverifiable_no_model_reported"
    assert monitor.stop_reason is None


def test_two_consecutive_timeouts_stop_the_batch() -> None:
    monitor = StopMonitor()
    monitor.observe_outcome(timed_out=True)
    monitor.observe_outcome(timed_out=False)  # resets
    monitor.observe_outcome(timed_out=True)
    with pytest.raises(StopBatchError) as error:
        monitor.observe_outcome(timed_out=True)
    assert error.value.reason == "consecutive_timeouts"


def test_smoke_stops_on_first_invalid_judge_output() -> None:
    monitor = StopMonitor(judge_mode="smoke")
    monitor.observe_judge_validity(True)
    with pytest.raises(StopBatchError) as error:
        monitor.observe_judge_validity(False)
    assert error.value.reason == "judge_invalid_output"


def test_pilot_invalid_rate_needs_four_calls_and_over_25_percent() -> None:
    monitor = StopMonitor(judge_mode="pilot")
    monitor.observe_judge_validity(False)  # 1/1 invalid, but fewer than 4 calls
    for _ in range(3):
        monitor.observe_judge_validity(True)  # 1/4 = 25%: not over the limit
    assert monitor.stop_reason is None
    with pytest.raises(StopBatchError) as error:
        monitor.observe_judge_validity(False)  # 2/5 = 40%
    assert error.value.reason == "judge_invalid_rate"


# --- real call path: the DeepSeek recording client ---------------------------


async def test_guard_blocks_the_deepseek_call_before_it_is_sent(
    config: PilotConfig, cases: dict[str, object]
) -> None:
    fake = FakeOpenAIClient()
    guard = _guard(tokens=5_000)  # below one 16000-token output reservation
    recorder = RecordingClient(
        fake, context=CallContext("b", "PQB-P07", "A"), guard=guard
    )
    request = cases["PQB-P07"].frozen_input.to_request()  # type: ignore[attr-defined]
    result = await run_condition_a(request, build_provider(recorder, config.model))
    assert result.status == "failed"
    assert fake.calls == 0  # nothing reached the endpoint
    assert recorder.records == []
    assert guard.monitor.stop_reason == "token_budget"


async def test_deepseek_usage_settles_and_unknown_usage_is_held(
    config: PilotConfig, cases: dict[str, object]
) -> None:
    guard = _guard(tokens=1_000_000, usd=5.0)
    fake = FakeOpenAIClient(FakeBehavior(raise_on_call={1: status_error(500)}))
    recorder = RecordingClient(
        fake, context=CallContext("b", "PQB-P01", "A"), guard=guard
    )
    request = cases["PQB-P01"].frozen_input.to_request()  # type: ignore[attr-defined]
    result = await run_condition_a(request, build_provider(recorder, config.model))
    assert result.status == "completed"
    statuses = [r.status for r in guard.ledger.reservations]
    assert statuses == ["held_unknown", "settled"]  # 500 then success
    assert guard.ledger.reservations[0].reserved_tokens > 16_000


async def test_batch_stops_on_the_real_call_path_and_keeps_records(
    config: PilotConfig, tmp_path: Path
) -> None:
    from prd_benchmark.artifacts import BatchLayout
    from prd_benchmark.batch import BatchOptions, run_batch

    guard = _guard(tokens=30_000, usd=5.0)  # room for a few calls, not a batch
    options = BatchOptions(
        batch_id="stop-test",
        mode="fake",
        output_root=tmp_path,
        case_ids=["PQB-P01", "PQB-P02"],
        guard=guard,
    )
    summary = await run_batch(options, config)
    assert summary.stop_reason == "token_budget"
    assert summary.aborted and "token_budget" in summary.aborted
    layout = BatchLayout(tmp_path, "stop-test")
    batch = json.loads((layout.runs / "batch.json").read_text(encoding="utf-8"))
    assert batch["stop"]["stop_reason"] == "token_budget"
    assert batch["budget"]["charged_tokens"] <= 30_000
    ledgers = list((tmp_path / "ledgers" / "stop-test").glob("generator-*.json"))
    assert len(ledgers) == 1
    # Everything already produced is kept; the second case never started.
    assert not (layout.runs / "PQB-P02").exists()


def test_budget_blockers_require_both_caps_and_verified_prices(
    config: PilotConfig,
) -> None:
    blockers = budget_blockers(config, "generator")
    assert "approvals.token_budget_limit is not set" in blockers
    assert "approvals.usd_budget_limit is not set" in blockers
    assert any("is not verified" in b for b in blockers)
    assert config.approvals.real_model_calls == "not_approved"
    assert config.approvals.judge_calls == "not_approved"
