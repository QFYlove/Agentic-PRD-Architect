"""Dated official price snapshots and per-call cost estimates.

A snapshot is copied by a person from an official price page and stored under
``pricing/``. Costs computed from it are *estimates*; only a bill
reconciliation turns them into verifiable costs. Nothing here fetches prices.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from prd_benchmark._yaml import load_yaml

PriceItem = Literal[
    "input_cache_miss",
    "input_cache_hit",
    "cache_write_5m",
    "cache_write_1h",
    "output",
]
#: Items billed for prompt tokens; reservations price input at the worst one.
INPUT_ITEMS: tuple[PriceItem, ...] = (
    "input_cache_miss",
    "input_cache_hit",
    "cache_write_5m",
    "cache_write_1h",
)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Price(_Strict):
    item: PriceItem
    usd_per_mtok: float = Field(ge=0)
    period: Literal["any", "peak", "offpeak"] = "any"


class PeakWindow(_Strict):
    days: tuple[Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"], ...]
    start_utc: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_utc: str = Field(pattern=r"^\d{2}:\d{2}$")


class PriceSnapshot(_Strict):
    snapshot_id: str
    provider: str
    model_id: str
    #: ``gateway_per_token``: prices declared by the gateway operator, entered
    #: by a person; acceptable only for a gateway explicitly allowed in config.
    billing: Literal["api_per_token", "gateway_per_token"]
    currency: Literal["USD"]
    source_url: str = Field(pattern=r"^https://")
    retrieved_at: str
    #: ``draft``: transcribed but not checked by a person against the page.
    status: Literal["draft", "verified"]
    verified_by: str | None = None
    prices: tuple[Price, ...] = Field(min_length=1)
    peak_windows: tuple[PeakWindow, ...] = ()
    #: Days the provider excludes from peak (e.g. public holidays). Not
    #: modelled; treating them as peak only overestimates.
    peak_exclusions: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        items = {p.item for p in self.prices}
        if "output" not in items or "input_cache_miss" not in items:
            raise ValueError(f"{self.snapshot_id}: needs input and output prices")
        if self.status == "verified" and not self.verified_by:
            raise ValueError(f"{self.snapshot_id}: verified snapshot needs verified_by")
        periods = {p.period for p in self.prices}
        if periods & {"peak", "offpeak"} and not self.peak_windows:
            raise ValueError(f"{self.snapshot_id}: peak prices need peak_windows")
        return self

    def is_peak(self, at: datetime) -> bool:
        at = at.astimezone(UTC)
        day = WEEKDAYS[at.weekday()]
        hhmm = at.strftime("%H:%M")
        return any(
            day in w.days and w.start_utc <= hhmm < w.end_utc for w in self.peak_windows
        )

    def price(self, item: PriceItem, at: datetime | None) -> float | None:
        """Price of ``item`` at ``at``; the higher period when ``at`` is unknown."""
        matching = [p for p in self.prices if p.item == item]
        if not matching:
            return None
        if at is None:
            return max(p.usd_per_mtok for p in matching)
        period = "peak" if self.is_peak(at) else "offpeak"
        exact = [p for p in matching if p.period in (period, "any")]
        return max(p.usd_per_mtok for p in (exact or matching))

    @property
    def worst_input_usd_per_mtok(self) -> float:
        return max(p.usd_per_mtok for p in self.prices if p.item in INPUT_ITEMS)

    @property
    def worst_output_usd_per_mtok(self) -> float:
        return max(p.usd_per_mtok for p in self.prices if p.item == "output")


def load_snapshot(path: Path) -> PriceSnapshot:
    return PriceSnapshot.model_validate(load_yaml(path))


def worst_case_usd(
    snapshot: PriceSnapshot, input_tokens: int, output_tokens: int
) -> float:
    return (
        input_tokens * snapshot.worst_input_usd_per_mtok
        + output_tokens * snapshot.worst_output_usd_per_mtok
    ) / 1_000_000


class UsageBreakdown(_Strict):
    """Token counts as reported by the provider; ``None`` means not reported."""

    input_cache_miss: int | None = None
    input_cache_hit: int | None = None
    cache_write: int | None = None
    output: int | None = None

    @property
    def complete(self) -> bool:
        return self.input_cache_miss is not None and self.output is not None

    @property
    def total(self) -> int | None:
        if not self.complete:
            return None
        return sum(
            v or 0
            for v in (
                self.input_cache_miss,
                self.input_cache_hit,
                self.cache_write,
                self.output,
            )
        )


def estimate_usd(
    snapshot: PriceSnapshot, usage: UsageBreakdown, at: datetime | None
) -> float | None:
    """Estimated cost of reported usage, or ``None`` when usage is incomplete.

    Cache writes are priced at the higher of the 5-minute and 1-hour rates,
    because the CLI does not say which duration it used.
    """
    if not usage.complete:
        return None

    def p(item: PriceItem) -> float:
        value = snapshot.price(item, at)
        if value is None:
            # No separate price published: fall back to the cache-miss rate.
            value = snapshot.price("input_cache_miss", at) or 0.0
        return value

    write_price = max(p("cache_write_5m"), p("cache_write_1h"))
    return (
        (usage.input_cache_miss or 0) * p("input_cache_miss")
        + (usage.input_cache_hit or 0) * p("input_cache_hit")
        + (usage.cache_write or 0) * write_price
        + (usage.output or 0) * p("output")
    ) / 1_000_000
