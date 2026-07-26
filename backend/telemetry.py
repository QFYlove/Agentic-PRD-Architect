from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from backend.config import Settings
from backend.schemas import TokenUsage


def add_usage(left: TokenUsage, right: TokenUsage) -> TokenUsage:
    input_tokens = left.input_tokens + right.input_tokens
    output_tokens = left.output_tokens + right.output_tokens
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def estimate_cost(
    usage: TokenUsage,
    settings: Settings,
    *,
    is_mock: bool,
) -> float | None:
    if is_mock:
        return 0.0
    if not settings.has_model_pricing:
        return None
    assert settings.model_input_price_per_million is not None
    assert settings.model_output_price_per_million is not None
    cost = Decimal(
        usage.input_tokens
    ) * settings.model_input_price_per_million / Decimal(1_000_000) + Decimal(
        usage.output_tokens
    ) * settings.model_output_price_per_million / Decimal(1_000_000)
    return float(cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
