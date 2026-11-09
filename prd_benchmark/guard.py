"""Budget reservation and stop conditions on the actual call path.

Every real request -- a DeepSeek call through ``RecordingClient`` or a Judge
call through ``ClaudeCodeJudge`` -- goes through one ``CallGuard``:

1. ``before_call`` estimates an upper bound on input tokens, adds the maximum
   output the request may produce, prices both at the snapshot's worst unit
   price, and refuses the call unless *both* the token and the dollar budget
   still have room (committed + outstanding + this reservation).
2. ``after_call`` settles the reservation with the reported usage. When usage
   is unknown (timeout, cancellation, interrupted stream, incomplete report)
   the full worst-case reservation stays charged; it is never released.
3. Stop conditions (model drift, consecutive timeouts, invalid judge output,
   budget reached, accounting errors) latch ``stop_reason``. Once latched,
   every later ``before_call`` refuses.

All amounts are estimates from price snapshots, never billed amounts.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from prd_benchmark.pricing import (
    PriceSnapshot,
    UsageBreakdown,
    estimate_usd,
    worst_case_usd,
)

Channel = Literal["generator", "judge"]
Estimator = Literal["utf8_bytes", "chars"]
JudgeMode = Literal["smoke", "pilot"]


class StopBatchError(RuntimeError):
    """A stop condition fired; the batch must not issue further calls."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class BudgetExceededError(StopBatchError):
    pass


class BudgetAccountingError(StopBatchError):
    pass


def input_token_upper_bound(text: str, estimator: Estimator = "utf8_bytes") -> int:
    """An upper bound on the tokens ``text`` can encode to.

    ``utf8_bytes`` is a hard bound for byte-level BPE tokenizers (every token
    covers at least one byte); it overestimates CJK text roughly 2-3x.
    ``chars`` is tighter but not guaranteed for every tokenizer.
    """
    if estimator == "chars":
        return len(text)
    return len(text.encode("utf-8"))


@dataclass
class Reservation:
    reservation_id: int
    channel: Channel
    label: str
    reserved_tokens: int
    reserved_usd: float
    created_at: str
    status: Literal["outstanding", "settled", "held_unknown"] = "outstanding"
    actual_tokens: int | None = None
    actual_usd: float | None = None
    note: str | None = None

    @property
    def charged_tokens(self) -> int:
        if self.status == "settled" and self.actual_tokens is not None:
            return self.actual_tokens
        return self.reserved_tokens

    @property
    def charged_usd(self) -> float:
        if self.status == "settled" and self.actual_usd is not None:
            return self.actual_usd
        return self.reserved_usd


@dataclass
class SpendLedger:
    """Token and dollar accounting shared by generator and judge calls.

    ``prior_tokens`` / ``prior_usd`` carry what earlier commands of the same
    batch charged (loaded from their ledger files), so the caps are batch-wide.
    """

    token_limit: int | None
    usd_limit: float | None
    prior_tokens: int = 0
    prior_usd: float = 0.0
    prior_by_channel: dict[str, dict[str, float]] = field(default_factory=dict)
    reservations: list[Reservation] = field(default_factory=list)

    @property
    def charged_tokens(self) -> int:
        return self.prior_tokens + sum(r.charged_tokens for r in self.reservations)

    @property
    def charged_usd(self) -> float:
        return self.prior_usd + sum(r.charged_usd for r in self.reservations)

    def reserve(
        self, channel: Channel, label: str, tokens: int, usd: float
    ) -> Reservation:
        if tokens < 0 or usd < 0:
            raise BudgetAccountingError("accounting", f"negative reservation {label}")
        if (
            self.token_limit is not None
            and self.charged_tokens + tokens > self.token_limit
        ):
            raise BudgetExceededError(
                "token_budget",
                f"{label}: {self.charged_tokens} + {tokens} > {self.token_limit}",
            )
        if self.usd_limit is not None and self.charged_usd + usd > self.usd_limit:
            raise BudgetExceededError(
                "cost_budget",
                f"{label}: {self.charged_usd:.4f} + {usd:.4f} > {self.usd_limit:.4f}",
            )
        reservation = Reservation(
            reservation_id=len(self.reservations) + 1,
            channel=channel,
            label=label,
            reserved_tokens=tokens,
            reserved_usd=round(usd, 6),
            created_at=datetime.now(UTC).isoformat(),
        )
        self.reservations.append(reservation)
        return reservation

    def settle(
        self,
        reservation: Reservation,
        actual_tokens: int | None,
        actual_usd: float | None,
        note: str | None = None,
    ) -> None:
        if reservation.status != "outstanding":
            raise BudgetAccountingError(
                "accounting", f"reservation {reservation.reservation_id} settled twice"
            )
        if actual_tokens is None or actual_usd is None:
            # Unknown usage: keep the worst case charged, permanently.
            reservation.status = "held_unknown"
        else:
            if actual_tokens < 0 or actual_usd < 0:
                raise BudgetAccountingError("accounting", "negative actual usage")
            reservation.status = "settled"
            reservation.actual_tokens = actual_tokens
            reservation.actual_usd = round(actual_usd, 6)
        reservation.note = note

    def summary(self) -> dict[str, Any]:
        by_channel: dict[str, dict[str, float]] = {
            ch: dict(values) for ch, values in self.prior_by_channel.items()
        }
        for r in self.reservations:
            entry = by_channel.setdefault(
                r.channel, {"tokens": 0, "usd": 0.0, "held_unknown_usd": 0.0}
            )
            entry["tokens"] += r.charged_tokens
            entry["usd"] = round(entry["usd"] + r.charged_usd, 6)
            if r.status == "held_unknown":
                entry["held_unknown_usd"] = round(
                    entry.get("held_unknown_usd", 0.0) + r.reserved_usd, 6
                )
        return {
            "token_limit": self.token_limit,
            "usd_limit": self.usd_limit,
            "charged_tokens": self.charged_tokens,
            "charged_usd_estimate": round(self.charged_usd, 6),
            "by_channel": by_channel,
            "cost_basis": "estimate_from_price_snapshot",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.summary(),
            "prior_tokens": self.prior_tokens,
            "prior_usd": self.prior_usd,
            "reservations": [asdict(r) for r in self.reservations],
        }


def load_prior(paths: list[Path]) -> tuple[int, float, dict[str, dict[str, float]]]:
    """Totals charged by earlier ledger files of the same batch."""
    tokens, usd = 0, 0.0
    by_channel: dict[str, dict[str, float]] = {}
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        for r in data.get("reservations", []):
            charged_t = (
                r["actual_tokens"] if r["status"] == "settled" else r["reserved_tokens"]
            )
            charged_u = (
                r["actual_usd"] if r["status"] == "settled" else r["reserved_usd"]
            )
            tokens += charged_t
            usd += charged_u
            entry = by_channel.setdefault(
                r["channel"], {"tokens": 0, "usd": 0.0, "held_unknown_usd": 0.0}
            )
            entry["tokens"] += charged_t
            entry["usd"] = round(entry["usd"] + charged_u, 6)
            if r["status"] == "held_unknown":
                entry["held_unknown_usd"] = round(
                    entry["held_unknown_usd"] + r["reserved_usd"], 6
                )
    return tokens, usd, by_channel


@dataclass
class StopMonitor:
    """Batch-level stop conditions, fed by every finished call."""

    judge_mode: JudgeMode = "smoke"
    max_consecutive_timeouts: int = 2
    pilot_min_judge_calls: int = 4
    pilot_max_invalid_rate: float = 0.25
    configured_models: dict[str, str | None] = field(default_factory=dict)
    models_seen: dict[str, list[str]] = field(default_factory=dict)
    missing_model_calls: dict[str, int] = field(default_factory=dict)
    consecutive_timeouts: int = 0
    judge_calls: int = 0
    judge_invalid: int = 0
    stop_reason: str | None = None
    stop_detail: str | None = None

    def _stop(self, reason: str, detail: str) -> None:
        if self.stop_reason is None:
            self.stop_reason, self.stop_detail = reason, detail
        raise StopBatchError(reason, detail)

    def check(self) -> None:
        if self.stop_reason is not None:
            raise StopBatchError(self.stop_reason, self.stop_detail or "")

    def latch(self, error: StopBatchError) -> None:
        if self.stop_reason is None:
            self.stop_reason, self.stop_detail = error.reason, error.detail

    def observe_model(self, channel: str, models: list[str]) -> None:
        if not models:
            self.missing_model_calls[channel] = (
                self.missing_model_calls.get(channel, 0) + 1
            )
            return
        seen = self.models_seen.setdefault(channel, [])
        for model in models:
            if model not in seen:
                seen.append(model)
        if len(seen) > 1:
            self._stop("model_drift", f"{channel}: {seen}")

    def observe_outcome(self, timed_out: bool) -> None:
        if timed_out:
            self.consecutive_timeouts += 1
            if self.consecutive_timeouts >= self.max_consecutive_timeouts:
                self._stop(
                    "consecutive_timeouts", f"{self.consecutive_timeouts} in a row"
                )
        else:
            self.consecutive_timeouts = 0

    def observe_judge_validity(self, valid: bool) -> None:
        self.judge_calls += 1
        if not valid:
            self.judge_invalid += 1
        if self.judge_mode == "smoke" and not valid:
            self._stop("judge_invalid_output", "smoke test stops on the first one")
        if (
            self.judge_mode == "pilot"
            and self.judge_calls >= self.pilot_min_judge_calls
            and self.judge_invalid / self.judge_calls > self.pilot_max_invalid_rate
        ):
            self._stop(
                "judge_invalid_rate",
                f"{self.judge_invalid}/{self.judge_calls} invalid",
            )

    def snapshot_verifiability(self) -> dict[str, str]:
        """Per channel: whether the served snapshot can be identified at all."""
        result: dict[str, str] = {}
        for channel in {*self.models_seen, *self.missing_model_calls}:
            seen = self.models_seen.get(channel, [])
            configured = self.configured_models.get(channel)
            if not seen:
                result[channel] = "unverifiable_no_model_reported"
            elif self.missing_model_calls.get(channel):
                result[channel] = "unverifiable_model_missing_on_some_calls"
            elif configured is not None and seen == [configured]:
                result[channel] = "unverifiable_alias_only"
            else:
                result[channel] = "reported_identifier_only"
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "stop_reason": self.stop_reason,
            "stop_detail": self.stop_detail,
            "models_seen": self.models_seen,
            "missing_model_calls": self.missing_model_calls,
            "snapshot_verifiability": self.snapshot_verifiability(),
            "judge_calls": self.judge_calls,
            "judge_invalid": self.judge_invalid,
            "judge_mode": self.judge_mode,
        }


@dataclass
class CallGuard:
    """Ledger + monitor + prices: the single gate every real call passes."""

    ledger: SpendLedger
    monitor: StopMonitor
    prices: dict[str, PriceSnapshot | None] = field(default_factory=dict)
    estimator: Estimator = "utf8_bytes"

    def before_call(
        self,
        channel: Channel,
        label: str,
        input_text: str,
        max_output_tokens: int,
        *,
        requests: int = 1,
    ) -> Reservation:
        """Reserve the worst case of one logical call, or refuse it.

        ``requests`` is the most API requests the call may make (a CLI run can
        make more than one); input and output are reserved for each.
        """
        try:
            self.monitor.check()
            if requests < 1 or max_output_tokens < 1:
                raise BudgetAccountingError("accounting", f"bad bounds for {label}")
            snapshot = self.prices.get(channel)
            tokens_in = input_token_upper_bound(input_text, self.estimator) * requests
            max_output_tokens *= requests
            tokens = tokens_in + max_output_tokens
            if snapshot is None:
                if self.ledger.usd_limit is not None:
                    raise BudgetAccountingError(
                        "accounting", f"no price snapshot for {channel}"
                    )
                usd = 0.0
            else:
                usd = worst_case_usd(snapshot, tokens_in, max_output_tokens)
            return self.ledger.reserve(channel, label, tokens, usd)
        except StopBatchError as error:
            self.monitor.latch(error)
            raise

    def after_call(
        self,
        reservation: Reservation,
        *,
        usage: UsageBreakdown | None,
        at: datetime | None,
        timed_out: bool,
        models: list[str] | None = None,
        note: str | None = None,
    ) -> None:
        """Settle, then run the stop checks (which may raise StopBatchError)."""
        snapshot = self.prices.get(reservation.channel)
        actual_tokens = usage.total if usage is not None else None
        if usage is None or actual_tokens is None:
            actual_usd = None
        elif snapshot is None:
            actual_usd = 0.0 if self.ledger.usd_limit is None else None
        else:
            actual_usd = estimate_usd(snapshot, usage, at)
        try:
            self.ledger.settle(reservation, actual_tokens, actual_usd, note)
            if models is not None:
                self.monitor.observe_model(reservation.channel, models)
            self.monitor.observe_outcome(timed_out)
            self._check_budget_reached()
        except StopBatchError as error:
            self.monitor.latch(error)
            raise

    def _check_budget_reached(self) -> None:
        ledger = self.ledger
        if (
            ledger.token_limit is not None
            and ledger.charged_tokens >= ledger.token_limit
        ):
            raise BudgetExceededError("token_budget", "limit reached")
        if ledger.usd_limit is not None and ledger.charged_usd >= ledger.usd_limit:
            raise BudgetExceededError("cost_budget", "limit reached")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ledger": self.ledger.to_dict(),
            "monitor": self.monitor.to_dict(),
            "estimator": self.estimator,
            "price_snapshots": {
                ch: (s.snapshot_id if s else None) for ch, s in self.prices.items()
            },
        }
