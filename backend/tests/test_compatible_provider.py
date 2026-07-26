from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from backend.errors import ProviderAuthenticationError, RetryableProviderError
from backend.providers.compatible import OpenAICompatibleLLMProvider
from backend.schemas import (
    EvaluationResult,
    ReviewRole,
    RevisionPlan,
    RoleReview,
    TokenUsage,
)


def usage() -> SimpleNamespace:
    return SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)


def response(value: object, *, include_usage: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(value)),
                finish_reason="stop",
            )
        ],
        usage=usage() if include_usage else None,
        model="provider-test-model",
    )


class FakeStream:
    def __init__(self, chunks: list[object]) -> None:
        self.chunks = iter(chunks)
        self.closed = False

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> object:
        try:
            return next(self.chunks)
        except StopIteration as error:
            raise StopAsyncIteration from error

    async def close(self) -> None:
        self.closed = True


class BlockingStream:
    def __init__(self) -> None:
        self.closed = False
        self.waiting = asyncio.Event()

    def __aiter__(self) -> BlockingStream:
        return self

    async def __anext__(self) -> object:
        self.waiting.set()
        await asyncio.Event().wait()
        raise StopAsyncIteration

    async def close(self) -> None:
        self.closed = True


class FakeCompletions:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def provider(
    outcomes: list[object],
    *,
    provider_name: str = "deepseek",
) -> tuple[OpenAICompatibleLLMProvider, FakeCompletions]:
    completions = FakeCompletions(outcomes)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return (
        OpenAICompatibleLLMProvider(
            provider_name=provider_name,
            api_key="not-a-real-key",
            base_url="https://provider.invalid",
            model="provider-test-model",
            request_timeout_seconds=3,
            extra_body=(
                {"thinking": {"type": "disabled"}}
                if provider_name == "deepseek"
                else None
            ),
            client=client,
        ),
        completions,
    )


async def collect_stream(adapter: OpenAICompatibleLLMProvider) -> list[Any]:
    return [
        event
        async for event in adapter.stream_prd(
            user_idea="Build a secure podcast product.",
            target_audience="Listeners",
            user_constraints="<script>do not execute</script>",
            iteration=1,
            revision_plan=None,
        )
    ]


def delta(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content=content))],
        usage=None,
        model="provider-test-model",
    )


async def test_streams_markdown_usage_and_closes_sdk_stream() -> None:
    stream = FakeStream(
        [
            delta("# PRD"),
            delta("\nBody"),
            SimpleNamespace(
                choices=[],
                usage=usage(),
                model="provider-test-model",
            ),
        ]
    )
    adapter, calls = provider([stream])

    events = await collect_stream(adapter)

    assert "".join(event.delta for event in events) == "# PRD\nBody"
    assert events[-1].usage == TokenUsage(
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
    )
    assert stream.closed
    assert calls.calls[0]["stream"] is True
    assert calls.calls[0]["stream_options"] == {"include_usage": True}
    assert calls.calls[0]["timeout"] == 3
    assert calls.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "<script>do not execute</script>" in calls.calls[0]["messages"][1]["content"]


async def test_glm_omits_deepseek_specific_thinking_parameter() -> None:
    adapter, calls = provider(
        [FakeStream([delta("# PRD"), SimpleNamespace(choices=[], usage=usage())])],
        provider_name="glm",
    )

    await collect_stream(adapter)

    assert "extra_body" not in calls.calls[0]


async def test_cancel_closes_in_flight_stream_without_relabeling_error() -> None:
    stream = BlockingStream()
    adapter, _ = provider([stream])
    task = asyncio.create_task(collect_stream(adapter))
    await asyncio.wait_for(stream.waiting.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert stream.closed


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            openai.AuthenticationError(
                "bad key",
                response=httpx.Response(
                    401,
                    request=httpx.Request("POST", "https://provider.invalid"),
                ),
                body=None,
            ),
            ProviderAuthenticationError,
        ),
        (
            openai.APITimeoutError(
                request=httpx.Request("POST", "https://provider.invalid")
            ),
            RetryableProviderError,
        ),
    ],
)
async def test_translates_sdk_errors(
    error: Exception,
    expected: type[Exception],
) -> None:
    adapter, _ = provider([error])

    with pytest.raises(expected):
        await collect_stream(adapter)


def valid_review() -> dict[str, object]:
    return {
        "role": "tech",
        "score": 82,
        "summary": "Feasible with bounded risks.",
        "strengths": ["Clear outcome"],
        "feedback": ["Add retry ownership."],
    }


def evaluation() -> EvaluationResult:
    reviews = [
        RoleReview(role=role, score=80, summary=f"{role.value} summary")
        for role in ReviewRole
    ]
    return EvaluationResult(
        tech=reviews[0],
        ux=reviews[1],
        biz=reviews[2],
        overall_score=80,
    )


async def test_structured_review_uses_native_json_mode_and_schema_prompt() -> None:
    adapter, calls = provider([response(valid_review())])

    result = await adapter.generate_review(
        role=ReviewRole.TECH,
        prd="# PRD",
        iteration=1,
    )

    assert RoleReview.model_validate(result.value).score == 82
    assert calls.calls[0]["response_format"] == {"type": "json_object"}
    assert "JSON Schema" in calls.calls[0]["messages"][0]["content"]
    assert '"additionalProperties":false' in calls.calls[0]["messages"][0]["content"]


async def test_invalid_structure_is_returned_for_workflow_repair() -> None:
    adapter, _ = provider([response({"role": "tech", "score": 999})])

    result = await adapter.generate_review(
        role=ReviewRole.TECH,
        prd="# PRD",
        iteration=1,
    )

    with pytest.raises(ValueError):
        RoleReview.model_validate(result.value)


async def test_revision_plan_and_repair_share_structured_contract() -> None:
    repaired = {
        "iteration": 1,
        "objective": "Repair invalid output.",
        "items": [],
        "user_override": None,
    }
    adapter, calls = provider([response(repaired), response(repaired)])

    plan_result = await adapter.generate_revision_plan(
        evaluation=evaluation(),
        iteration=1,
        user_override=None,
    )
    repair_result = await adapter.repair_structured(
        kind="revision_plan",
        raw_value={"invalid": True},
        validation_error="items are invalid",
    )

    assert RevisionPlan.model_validate(plan_result.value).iteration == 1
    assert RevisionPlan.model_validate(repair_result.value).iteration == 1
    assert "RevisionPlan" in calls.calls[1]["messages"][0]["content"]
    assert "exactly once" in calls.calls[1]["messages"][1]["content"]


async def test_missing_usage_fails_predictably() -> None:
    adapter, _ = provider([response(valid_review(), include_usage=False)])

    with pytest.raises(RetryableProviderError, match="omitted token usage"):
        await adapter.generate_review(
            role=ReviewRole.TECH,
            prd="# PRD",
            iteration=1,
        )
