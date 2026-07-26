from decimal import Decimal

from backend.schemas import TokenUsage
from backend.telemetry import add_usage, estimate_cost
from backend.tests.helpers import make_settings


def test_usage_addition_and_known_cost() -> None:
    usage = add_usage(
        TokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
        TokenUsage(input_tokens=200, output_tokens=100, total_tokens=300),
    )
    settings = make_settings(
        model_input_price_per_million=Decimal("2"),
        model_output_price_per_million=Decimal("8"),
    )

    assert usage.total_tokens == 450
    assert estimate_cost(usage, settings, is_mock=False) == 0.0018


def test_unknown_real_cost_is_none_and_mock_cost_is_zero() -> None:
    usage = TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)
    settings = make_settings()

    assert estimate_cost(usage, settings, is_mock=False) is None
    assert estimate_cost(usage, settings, is_mock=True) == 0.0
