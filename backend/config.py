from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    frontend_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:4321",
            "http://127.0.0.1:4321",
        ]
    )

    enable_mock_llm: bool = True
    llm_provider: Literal["deepseek", "glm"] = "deepseek"
    llm_request_timeout_seconds: float = Field(default=90.0, gt=0, le=600)
    deepseek_api_key: SecretStr | None = Field(default=None, repr=False)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    glm_api_key: SecretStr | None = Field(default=None, repr=False)
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "glm-5.2"
    model_input_price_per_million: Decimal | None = Field(default=None, ge=0)
    model_output_price_per_million: Decimal | None = Field(default=None, ge=0)

    mock_delays_enabled: bool = True
    mock_chunk_size: int = Field(default=72, ge=1, le=10_000)
    mock_generator_delay_seconds: float = Field(default=0.01, ge=0, le=10)
    mock_reviewer_delay_seconds: float = Field(default=0.02, ge=0, le=10)
    mock_optimizer_delay_seconds: float = Field(default=0.02, ge=0, le=10)
    e2e_test_mode: bool = False

    default_quality_threshold: float = Field(default=85.0, ge=50, le=100)
    default_max_iterations: int = Field(default=3, ge=1, le=5)
    max_concurrent_runs: int = Field(default=4, ge=1, le=32)
    max_retained_runs: int = Field(default=100, ge=1, le=10_000)
    run_ttl_seconds: int = Field(default=2_592_000, ge=60)
    cleanup_interval_seconds: int = Field(default=60, ge=5)
    event_buffer_size: int = Field(default=1000, ge=10, le=100_000)
    sse_heartbeat_seconds: int = Field(default=15, ge=5, le=300)
    database_path: str = "data/agentic-prd.sqlite3"

    generator_timeout_seconds: int = Field(default=240, ge=1)
    reviewer_timeout_seconds: int = Field(default=45, ge=1)
    optimizer_timeout_seconds: int = Field(default=60, ge=1)
    run_timeout_seconds: int = Field(default=600, ge=10)

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def parse_frontend_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator(
        "deepseek_api_key",
        "glm_api_key",
        "model_input_price_per_million",
        "model_output_price_per_million",
        mode="before",
    )
    @classmethod
    def empty_optional_values_are_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("frontend_origins")
    @classmethod
    def validate_frontend_origins(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("At least one frontend origin is required")
        for origin in value:
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"Invalid frontend origin: {origin}")
        return value

    @model_validator(mode="after")
    def validate_provider_configuration(self) -> Self:
        if self.e2e_test_mode and self.app_env != "test":
            raise ValueError("E2E_TEST_MODE is only allowed when APP_ENV=test")
        if not self.enable_mock_llm:
            if self.llm_provider == "deepseek" and self.deepseek_api_key is None:
                raise ValueError(
                    "DEEPSEEK_API_KEY is required for the DeepSeek provider"
                )
            if self.llm_provider == "glm" and self.glm_api_key is None:
                raise ValueError("GLM_API_KEY is required for the GLM provider")
            selected_model = (
                self.deepseek_model
                if self.llm_provider == "deepseek"
                else self.glm_model
            )
            if not selected_model.strip():
                raise ValueError("The selected provider model cannot be empty")

        prices = (
            self.model_input_price_per_million,
            self.model_output_price_per_million,
        )
        if any(price is None for price in prices) and not all(
            price is None for price in prices
        ):
            raise ValueError("Both model input and output prices must be configured")
        return self

    @property
    def has_model_pricing(self) -> bool:
        return (
            self.model_input_price_per_million is not None
            and self.model_output_price_per_million is not None
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
