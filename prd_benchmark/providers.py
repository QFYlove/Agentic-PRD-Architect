"""Construct the product provider around a recording client."""

from __future__ import annotations

import os
from typing import Any

from backend.providers.compatible import OpenAICompatibleLLMProvider
from prd_benchmark.config import ModelConfig

# DeepSeek thinking mode, exactly as the product hardcodes it (backend/main.py).
THINKING_DISABLED: dict[str, object] = {"thinking": {"type": "disabled"}}


class RealCallsBlockedError(RuntimeError):
    """Raised when something tries to build a billed client while gated."""


def build_provider(client: Any, model: ModelConfig) -> OpenAICompatibleLLMProvider:
    """The product's real provider class, with parameters mirroring real mode.

    The client is injected, so the provider never constructs its own
    ``AsyncOpenAI`` and never sees an API key; ``api_key`` below is unused.
    """
    return OpenAICompatibleLLMProvider(
        provider_name=model.provider_id,
        api_key="injected-client",
        base_url=model.base_url,
        model=model.model_id,
        request_timeout_seconds=model.request_timeout_seconds,
        max_output_tokens=model.max_output_tokens,
        extra_body=dict(THINKING_DISABLED),
        client=client,
    )


def build_real_client(model: ModelConfig, *, blockers: list[str]) -> Any:
    """A billed ``AsyncOpenAI`` client; refuses unless every gate is open.

    The key is read from the process environment at this point only. It is
    passed straight to the SDK and is never logged, returned, or written.
    """
    if blockers:
        raise RealCallsBlockedError("; ".join(blockers))
    api_key = os.environ.get(model.api_key_env)
    if not api_key:
        raise RealCallsBlockedError(f"{model.api_key_env} is not set")
    from openai import AsyncOpenAI

    return AsyncOpenAI(
        api_key=api_key,
        base_url=model.base_url,
        timeout=model.request_timeout_seconds,
        max_retries=0,
    )
