from __future__ import annotations

from typing import Any

import pytest
from openai.types.chat import ChatCompletionChunk

from backend.prd_document import PRD_COMPLETION_MARKER
from prd_benchmark.cases import Case
from prd_benchmark.config import PilotConfig
from prd_benchmark.fake_openai import FakeBehavior, FakeOpenAIClient
from prd_benchmark.providers import build_provider
from prd_benchmark.recording import CallContext, RecordingClient
from prd_benchmark.run_single import run_condition_a
from prd_benchmark.run_workflow import run_condition_b

USAGE = {
    "prompt_tokens": 10,
    "completion_tokens": 5,
    "total_tokens": 15,
    "prompt_cache_hit_tokens": 4,
    "prompt_cache_miss_tokens": 6,
}


def _chunk(
    model: str,
    content: str | None = None,
    finish: str | None = None,
    usage: dict[str, int] | None = None,
) -> ChatCompletionChunk:
    """A real SDK chunk object (not a dict)."""
    data: dict[str, Any] = {
        "id": "x",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": model,
        "choices": (
            []
            if usage
            else [{"index": 0, "delta": {"content": content}, "finish_reason": finish}]
        ),
    }
    if usage:
        data["usage"] = usage
    return ChatCompletionChunk.model_validate(data)


class _Stream:
    def __init__(self, chunks: list[ChatCompletionChunk]) -> None:
        self._chunks = iter(chunks)

    def __aiter__(self) -> _Stream:
        return self

    async def __anext__(self) -> ChatCompletionChunk:
        try:
            return next(self._chunks)
        except StopIteration:
            raise StopAsyncIteration from None

    async def close(self) -> None:
        return None


class _SdkObjectClient:
    def __init__(self, chunks: list[ChatCompletionChunk]) -> None:
        self._chunks = chunks
        self.chat = self
        self.completions = self

    async def create(self, **kwargs: Any) -> _Stream:
        return _Stream(self._chunks)


async def _stream_once(config: PilotConfig, inner: Any) -> RecordingClient:
    recorder = RecordingClient(inner, context=CallContext("t", "PQB-P01", "A"))
    provider = build_provider(recorder, config.model)
    async for _ in provider.stream_prd(
        user_idea="为技术阅读平台增加文章收藏功能。",
        target_audience=None,
        user_constraints=None,
        iteration=1,
        revision_plan=None,
        output_language="zh",
    ):
        pass
    return recorder


TEXT = f"正文\n{PRD_COMPLETION_MARKER}"


async def test_server_model_differing_from_alias_is_recorded(
    config: PilotConfig,
) -> None:
    fake = FakeOpenAIClient(FakeBehavior(response_model="deepseek-v4.1-flash-1017"))
    [call] = (await _stream_once(config, fake)).records
    assert call.configured_model == "deepseek-flash"
    assert call.response_model == "deepseek-v4.1-flash-1017"
    assert not call.response_model_missing


async def test_model_only_on_the_usage_chunk_of_sdk_objects(
    config: PilotConfig,
) -> None:
    chunks = [_chunk("", TEXT), _chunk("", None, "stop"), _chunk("snap-a", usage=USAGE)]
    [call] = (await _stream_once(config, _SdkObjectClient(chunks))).records
    assert call.response_model == "snap-a"
    assert call.response_models_seen == ["snap-a"]
    assert (call.cache_hit_tokens, call.cache_miss_tokens) == (4, 6)
    assert call.total_tokens == 15 and call.outcome == "ok"


async def test_model_change_within_one_stream_is_kept(config: PilotConfig) -> None:
    chunks = [
        _chunk("snap-a", TEXT),
        _chunk("snap-b", None, "stop"),
        _chunk("snap-b", usage=USAGE),
    ]
    [call] = (await _stream_once(config, _SdkObjectClient(chunks))).records
    assert call.response_model == "snap-a"
    assert call.response_models_seen == ["snap-a", "snap-b"]


@pytest.mark.parametrize("case_id", [f"PQB-P0{n}" for n in range(1, 9)])
async def test_a_and_b_v1_send_identical_first_generator_requests(
    config: PilotConfig, cases: dict[str, Case], case_id: str
) -> None:
    request = cases[case_id].frozen_input.to_request()
    rec_a = RecordingClient(FakeOpenAIClient(), context=CallContext("t", case_id, "A"))
    rec_b = RecordingClient(FakeOpenAIClient(), context=CallContext("t", case_id, "B"))
    await run_condition_a(request, build_provider(rec_a, config.model))
    await run_condition_b(
        request,
        build_provider(rec_b, config.model),
        model=config.model,
        condition=config.conditions.B,
    )

    def first(recorder: RecordingClient) -> str:
        return next(
            c.request_sha256
            for c in recorder.records
            if c.node == "generator" and c.version == 1
        )

    assert first(rec_a) == first(rec_b)
