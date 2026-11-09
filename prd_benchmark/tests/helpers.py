from __future__ import annotations

import httpx
import openai

from backend.providers.compatible import OpenAICompatibleLLMProvider
from prd_benchmark.config import PilotConfig
from prd_benchmark.fake_openai import FakeBehavior, FakeOpenAIClient
from prd_benchmark.providers import build_provider
from prd_benchmark.recording import CallContext, RecordingClient, TokenBudget


def status_error(status: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    response = httpx.Response(status, request=request)
    errors: dict[int, type[openai.APIStatusError]] = {
        404: openai.NotFoundError,
        429: openai.RateLimitError,
        500: openai.InternalServerError,
    }
    return errors[status]("simulated", response=response, body=None)


def recorded_provider(
    config: PilotConfig,
    behavior: FakeBehavior | None = None,
    *,
    condition: str = "A",
    budget: TokenBudget | None = None,
) -> tuple[RecordingClient, OpenAICompatibleLLMProvider]:
    fake = FakeOpenAIClient(behavior)
    recorder = RecordingClient(
        fake,
        context=CallContext("test-batch", "PQB-P01", condition),
        budget=budget,
    )
    return recorder, build_provider(recorder, config.model)
