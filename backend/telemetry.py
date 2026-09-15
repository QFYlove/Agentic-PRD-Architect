from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from backend.config import Settings
from backend.provider_catalog import ModelPricing
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
    settings: Settings | None = None,
    *,
    is_mock: bool,
    pricing: ModelPricing | None = None,
) -> float | None:
    if is_mock:
        return 0.0
    if pricing is not None:
        input_price, output_price = (
            pricing.input_per_million,
            pricing.output_per_million,
        )
    else:
        if settings is None or not settings.has_model_pricing:
            return None
        input_price, output_price = (
            settings.model_input_price_per_million,
            settings.model_output_price_per_million,
        )
    if input_price is None or output_price is None:
        return None
    cost = Decimal(usage.input_tokens) * input_price / Decimal(1_000_000) + Decimal(
        usage.output_tokens
    ) * output_price / Decimal(1_000_000)
    return float(cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
