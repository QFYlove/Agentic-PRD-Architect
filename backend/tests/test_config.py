from decimal import Decimal

import pytest
from pydantic import SecretStr, ValidationError

from backend.config import Settings


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)


def test_default_settings_are_mock_first() -> None:
    settings = make_settings()

    assert settings.enable_mock_llm is True
    assert settings.default_max_iterations == 3
    assert settings.frontend_origins == [
        "http://localhost:4321",
        "http://127.0.0.1:4321",
    ]
    assert settings.has_model_pricing is False


def test_origins_accept_comma_separated_environment_format() -> None:
    settings = make_settings(
        frontend_origins="http://localhost:4321,http://127.0.0.1:4321"
    )

    assert settings.frontend_origins == [
        "http://localhost:4321",
        "http://127.0.0.1:4321",
    ]


def test_settings_load_valid_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_PORT", "8123")
    monkeypatch.setenv("DEFAULT_QUALITY_THRESHOLD", "90.5")
    monkeypatch.setenv("MAX_CONCURRENT_RUNS", "8")

    settings = make_settings()

    assert settings.app_port == 8123
    assert settings.default_quality_threshold == 90.5
    assert settings.max_concurrent_runs == 8


def test_real_provider_requires_key_and_model() -> None:
    with pytest.raises(ValidationError, match="DEEPSEEK_API_KEY"):
        make_settings(enable_mock_llm=False)


def test_real_provider_accepts_secret_without_exposing_it() -> None:
    settings = make_settings(
        enable_mock_llm=False,
        deepseek_api_key=SecretStr("test-secret"),
        deepseek_model="test-model",
    )

    assert "test-secret" not in repr(settings)
    assert "test-secret" not in str(settings)


def test_glm_provider_requires_its_own_key() -> None:
    with pytest.raises(ValidationError, match="GLM_API_KEY"):
        make_settings(enable_mock_llm=False, llm_provider="glm")

    settings = make_settings(
        enable_mock_llm=False,
        llm_provider="glm",
        glm_api_key=SecretStr("glm-secret"),
    )

    assert settings.glm_model == "glm-5.2"
    assert "glm-secret" not in repr(settings)


def test_pricing_requires_both_sides() -> None:
    with pytest.raises(ValidationError, match="Both model input and output prices"):
        make_settings(model_input_price_per_million=Decimal("1.25"))


def test_known_pricing_is_available() -> None:
    settings = make_settings(
        model_input_price_per_million=Decimal("1.25"),
        model_output_price_per_million=Decimal("5.00"),
    )

    assert settings.has_model_pricing is True


def test_invalid_port_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(app_port=70_000)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("default_quality_threshold", 49),
        ("default_quality_threshold", 101),
        ("default_max_iterations", 0),
        ("default_max_iterations", 6),
        ("max_concurrent_runs", 0),
        ("run_ttl_seconds", 59),
        ("event_buffer_size", 9),
        ("sse_heartbeat_seconds", 4),
        ("generator_timeout_seconds", 0),
    ],
)
def test_invalid_operational_value_is_rejected(
    field: str,
    value: int,
) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{field: value})


def test_e2e_test_mode_is_rejected_outside_test_environment() -> None:
    with pytest.raises(ValidationError, match="only allowed"):
        make_settings(app_env="development", e2e_test_mode=True)
