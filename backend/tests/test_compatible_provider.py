from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from backend.errors import (
    InvalidModelError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderForbiddenError,
    ProviderInsufficientBalanceError,
    ProviderRequestRejectedError,
    RetryableProviderError,
)
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
    max_output_tokens: int | None = None,
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
            max_output_tokens=max_output_tokens,
            extra_body={"thinking": {"type": "disabled"}},
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


async def test_glm_disables_thinking_for_compatible_streaming() -> None:
    adapter, calls = provider(
        [FakeStream([delta("# PRD"), SimpleNamespace(choices=[], usage=usage())])],
        provider_name="glm",
    )

    await collect_stream(adapter)

    assert calls.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}


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


def status_error(status_code: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://provider.invalid")
    response = httpx.Response(status_code, request=request)
    return openai.APIStatusError(
        "provider said: sk-secret-key-leak",
        response=response,
        body=None,
    )


@pytest.mark.parametrize(
    ("status_code", "expected", "code", "retryable"),
    [
        (400, InvalidModelError, "PROVIDER_MODEL_INVALID", False),
        (401, ProviderAuthenticationError, "PROVIDER_AUTHENTICATION_FAILED", False),
        (
            402,
            ProviderInsufficientBalanceError,
            "PROVIDER_INSUFFICIENT_BALANCE",
            False,
        ),
        (403, ProviderForbiddenError, "PROVIDER_FORBIDDEN", False),
        (404, InvalidModelError, "PROVIDER_MODEL_INVALID", False),
        (408, RetryableProviderError, "PROVIDER_TEMPORARY_ERROR", True),
        (409, RetryableProviderError, "PROVIDER_TEMPORARY_ERROR", True),
        (422, ProviderRequestRejectedError, "PROVIDER_REQUEST_REJECTED", False),
        (429, RetryableProviderError, "PROVIDER_TEMPORARY_ERROR", True),
        (500, RetryableProviderError, "PROVIDER_TEMPORARY_ERROR", True),
        (502, RetryableProviderError, "PROVIDER_TEMPORARY_ERROR", True),
        (503, RetryableProviderError, "PROVIDER_TEMPORARY_ERROR", True),
    ],
)
async def test_status_codes_map_to_stable_codes_without_leaking_detail(
    status_code: int,
    expected: type[ProviderError],
    code: str,
    retryable: bool,
) -> None:
    adapter, _ = provider([status_error(status_code)])

    with pytest.raises(expected) as excinfo:
        await collect_stream(adapter)

    assert excinfo.value.code == code
    assert excinfo.value.retryable is retryable
    # The user-facing message never carries provider-supplied text.
    assert "sk-secret-key-leak" not in excinfo.value.user_message


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (402, ProviderInsufficientBalanceError),
        (403, ProviderForbiddenError),
        (429, RetryableProviderError),
    ],
)
async def test_structured_calls_share_the_status_mapping(
    status_code: int,
    expected: type[ProviderError],
) -> None:
    adapter, _ = provider([status_error(status_code)])

    with pytest.raises(expected):
        await adapter.generate_review(
            role=ReviewRole.TECH,
            prd="# PRD",
            iteration=1,
        )


async def test_unmapped_status_is_left_untranslated() -> None:
    adapter, _ = provider([status_error(418)])

    with pytest.raises(openai.APIStatusError):
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


def closing_delta(content: str, finish_reason: str) -> SimpleNamespace:
    """The chunk that closes a choice: it carries the real ``finish_reason``."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
        usage=None,
        model="provider-test-model",
    )


def usage_only_chunk() -> SimpleNamespace:
    return SimpleNamespace(choices=[], usage=usage(), model="provider-test-model")


async def test_max_tokens_is_sent_top_level_and_leaves_extra_body_untouched() -> None:
    """The output ceiling must be ours, not the endpoint's undocumented default."""
    adapter, calls = provider(
        [FakeStream([delta("# PRD"), usage_only_chunk()])],
        max_output_tokens=16_000,
    )

    await collect_stream(adapter)

    assert calls.calls[0]["max_tokens"] == 16_000
    assert calls.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}


async def test_structured_calls_send_the_same_output_ceiling() -> None:
    adapter, calls = provider([response(valid_review())], max_output_tokens=12_000)

    await adapter.generate_review(role=ReviewRole.TECH, prd="# PRD", iteration=1)

    assert calls.calls[0]["max_tokens"] == 12_000


async def test_unset_ceiling_omits_max_tokens_entirely() -> None:
    adapter, calls = provider([FakeStream([delta("# PRD"), usage_only_chunk()])])

    await collect_stream(adapter)

    assert "max_tokens" not in calls.calls[0]


@pytest.mark.parametrize(
    "reason",
    ["stop", "length", "content_filter", "insufficient_system_resource"],
)
async def test_streaming_reports_the_providers_own_finish_reason(reason: str) -> None:
    """The reason used to be hardcoded to ``stop``, which hid every truncation."""
    adapter, _ = provider(
        [
            FakeStream(
                [delta("# PRD"), closing_delta("\nBody", reason), usage_only_chunk()]
            )
        ]
    )

    events = await collect_stream(adapter)

    terminal = events[-1]
    assert terminal.usage is not None
    assert terminal.finish_reason == reason
    assert "".join(event.delta for event in events) == "# PRD\nBody"


async def test_absent_finish_reason_stays_absent_rather_than_becoming_stop() -> None:
    adapter, _ = provider([FakeStream([delta("# PRD"), usage_only_chunk()])])

    events = await collect_stream(adapter)

    assert events[-1].finish_reason is None


async def test_chinese_language_directive_reaches_generator_and_reviewer() -> None:
    stream_adapter, stream_calls = provider(
        [FakeStream([delta("# 产品需求文档"), usage_only_chunk()])]
    )
    async for _ in stream_adapter.stream_prd(
        user_idea="做一个播客按集付费的订阅产品。",
        target_audience="听众",
        user_constraints=None,
        iteration=1,
        revision_plan=None,
        output_language="zh",
    ):
        pass
    review_adapter, review_calls = provider([response(valid_review())])
    await review_adapter.generate_review(
        role=ReviewRole.BIZ,
        prd="# 产品需求文档",
        iteration=1,
        output_language="zh",
    )

    for calls in (stream_calls, review_calls):
        assert "Chinese (简体中文)" in calls.calls[0]["messages"][0]["content"]


async def test_baseline_prd_is_handed_to_the_generator_as_untrusted_data() -> None:
    """Without the previous document in the prompt, every round is a rewrite."""
    adapter, calls = provider([FakeStream([delta("# PRD"), usage_only_chunk()])])

    async for _ in adapter.stream_prd(
        user_idea="Build a podcast micro-subscription.",
        target_audience=None,
        user_constraints=None,
        iteration=2,
        revision_plan=None,
        baseline_prd="# Baseline PRD\n## Keep This Section",
    ):
        pass

    user_message = calls.calls[0]["messages"][1]["content"]
    assert "## Keep This Section" in user_message
    assert "untrusted product data" in user_message
