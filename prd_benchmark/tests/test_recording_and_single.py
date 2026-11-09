from __future__ import annotations

from typing import Any

import pytest

from backend.errors import InvalidModelError
from prd_benchmark.config import PilotConfig
from prd_benchmark.fake_openai import FakeBehavior
from prd_benchmark.recording import (
    BudgetExceededError,
    CallContext,
    RecordingClient,
    TokenBudget,
    classify,
)
from prd_benchmark.run_single import run_condition_a
from prd_benchmark.tests.helpers import recorded_provider, status_error


def _request(cases: dict[str, Any]) -> Any:
    return cases["PQB-P01"].frozen_input.to_request()


async def test_records_raw_response_model_tokens_and_first_token(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    recorder, provider = recorded_provider(config)
    result = await run_condition_a(_request(cases), provider)
    assert result.status == "completed"
    assert result.content and "<!-- PRD_COMPLETE -->" not in result.content
    [call] = recorder.records
    assert call.node == "generator" and call.version == 1 and call.attempt == 1
    assert call.configured_model == "deepseek-flash"
    assert call.response_model == "deepseek-flash"
    assert not call.response_model_missing
    assert call.outcome == "ok" and call.http_status == 200
    assert call.finish_reason == "stop"
    assert call.input_tokens and call.output_tokens
    assert call.total_tokens == call.input_tokens + call.output_tokens
    assert call.cache_hit_tokens is not None and call.cache_miss_tokens is not None
    assert call.first_token_seconds is not None
    assert "prompt_cache_hit_tokens" in call.usage_raw_keys


async def test_missing_response_model_is_not_backfilled(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    recorder, provider = recorded_provider(
        config, FakeBehavior(response_model=None, include_cache_fields=False)
    )
    await run_condition_a(_request(cases), provider)
    [call] = recorder.records
    # The product provider would fall back to "deepseek-flash" here; the
    # recorder must report that the server said nothing.
    assert call.response_model is None
    assert call.response_model_missing
    assert call.cache_hit_tokens is None


async def test_unfinished_output_is_retried_and_both_attempts_recorded(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    recorder, provider = recorded_provider(
        config, FakeBehavior(unfinished_generator_calls={1})
    )
    result = await run_condition_a(_request(cases), provider)
    assert result.status == "completed"
    assert [a.outcome for a in result.attempts] == ["retryable_error", "ok"]
    assert result.attempts[0].error_code == "PROVIDER_OUTPUT_UNFINISHED"
    assert [c.attempt for c in recorder.records] == [1, 2]
    # The failed attempt's tokens are kept, unlike the product's snapshot.
    assert recorder.records[0].output_tokens


async def test_retryable_status_then_success(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    recorder, provider = recorded_provider(
        config, FakeBehavior(raise_on_call={1: status_error(429)})
    )
    result = await run_condition_a(_request(cases), provider)
    assert result.status == "completed"
    first = recorder.records[0]
    assert first.outcome == "error"
    assert first.http_status == 429
    assert first.error_class == "RateLimitError"


async def test_invalid_model_is_not_retried(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    recorder, provider = recorded_provider(
        config, FakeBehavior(raise_on_call={1: status_error(404)})
    )
    result = await run_condition_a(_request(cases), provider)
    assert result.status == "failed"
    assert result.error_code == InvalidModelError.code
    assert len(recorder.records) == 1


async def test_two_failed_attempts_fail_the_run(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    _, provider = recorded_provider(
        config, FakeBehavior(unfinished_generator_calls={1, 2})
    )
    result = await run_condition_a(_request(cases), provider)
    assert result.status == "failed"
    assert result.content is None
    assert len(result.attempts) == 2


async def test_budget_blocks_calls_after_the_cap() -> None:
    class Inner:
        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**kwargs: Any) -> dict[str, Any]:
                    return {
                        "model": "deepseek-flash",
                        "choices": [{"message": {"content": "{}"}}],
                        "usage": {"prompt_tokens": 7, "completion_tokens": 3,
                                  "total_tokens": 10},
                    }  # fmt: skip

    budget = TokenBudget(limit=10)
    client = RecordingClient(Inner(), context=CallContext("b", "c", "A"), budget=budget)
    await client.create(model="m", messages=[], stream=False)
    assert budget.used == 10
    with pytest.raises(BudgetExceededError):
        await client.create(model="m", messages=[], stream=False)
    assert len(client.records) == 1


def test_classify_reads_the_product_payload() -> None:
    def kwargs(payload: str, stream: bool = False) -> dict[str, Any]:
        content = f"x\n<user_input_json>\n{payload}\n</user_input_json>"
        return {"stream": stream, "messages": [{"role": "user", "content": content}]}

    assert classify(kwargs('{"iteration": 2}', stream=True)) == ("generator", None, 2)
    assert classify(kwargs('{"required_role": "ux", "prd": "p", "iteration": 3}')) == (
        "ux_reviewer",
        "ux",
        3,
    )
    assert classify(kwargs('{"evaluation": {}, "iteration": 1}')) == (
        "optimizer",
        None,
        1,
    )
    repair = '{"task": "Repair the invalid structured result exactly once.", '
    repair += '"required_role": "biz"}'
    assert classify(kwargs(repair)) == ("repair", "biz", None)
