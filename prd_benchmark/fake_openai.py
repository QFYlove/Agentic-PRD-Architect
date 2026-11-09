"""In-process, scripted stand-in for an OpenAI-compatible endpoint.

Used for dry runs and tests. It exercises the product's real
``OpenAICompatibleLLMProvider`` (prompt assembly, streaming, finish-reason and
end-marker validation, structured parsing) without any network access. Its
documents are deliberately generic: they prove the pipeline works and say
nothing about PRD quality.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any

from backend.prd_document import PRD_COMPLETION_MARKER
from prd_benchmark.recording import classify, parse_payload

FAKE_MODEL_ID = "deepseek-flash"


@dataclass
class FakeBehavior:
    response_model: str | None = FAKE_MODEL_ID
    include_cache_fields: bool = True
    raise_on_call: dict[int, BaseException] = field(default_factory=dict)
    unfinished_generator_calls: set[int] = field(default_factory=set)
    invalid_review_calls: set[int] = field(default_factory=set)
    review_scores: dict[int, int] = field(default_factory=lambda: {1: 80})
    default_review_score: int = 90
    must_fix_iterations: set[int] = field(default_factory=lambda: {1})
    chunk_size: int = 160
    delay_seconds: float = 0.0


def fake_prd(payload: dict[str, Any]) -> str:
    baseline = payload.get("baseline_prd")
    iteration = payload.get("iteration", 1)
    if isinstance(baseline, str) and baseline:
        body = (
            f"{baseline}\n\n## 第 {iteration} 版修订\n\n已按修订计划逐项处理评审意见。"
        )
    else:
        body = "\n\n".join(
            [
                "# 产品需求文档（模拟输出）",
                f"## 背景与目标\n\n{payload.get('user_idea') or ''}",
                f"## 目标用户\n\n{payload.get('target_audience') or '未提供'}",
                f"## 约束\n\n{payload.get('user_constraints') or '未提供'}",
                "## 功能需求\n\n1. 按上述需求实现核心流程。",
                "## 验收标准\n\n- 核心流程可以端到端完成。",
            ]
        )
    return body


def _usage(behavior: FakeBehavior, messages: Any, text: str) -> dict[str, int]:
    prompt = max(1, len(json.dumps(messages, ensure_ascii=False)) // 3)
    completion = max(1, len(text) // 2)
    usage = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }
    if behavior.include_cache_fields:
        usage["prompt_cache_hit_tokens"] = prompt // 2
        usage["prompt_cache_miss_tokens"] = prompt - prompt // 2
    return usage


class _FakeStream:
    def __init__(self, chunks: list[dict[str, Any]], delay: float) -> None:
        self._chunks = iter(chunks)
        self._delay = delay
        self.closed = False

    def __aiter__(self) -> _FakeStream:
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._delay:
            await asyncio.sleep(self._delay)
        try:
            return next(self._chunks)
        except StopIteration:
            raise StopAsyncIteration from None

    async def close(self) -> None:
        self.closed = True


class _Completions:
    def __init__(self, owner: FakeOpenAIClient) -> None:
        self._owner = owner

    async def create(self, **kwargs: Any) -> Any:
        return await self._owner.create(**kwargs)


class _Chat:
    def __init__(self, owner: FakeOpenAIClient) -> None:
        self.completions = _Completions(owner)


class FakeOpenAIClient:
    def __init__(self, behavior: FakeBehavior | None = None) -> None:
        self.behavior = behavior or FakeBehavior()
        self.chat = _Chat(self)
        self.calls = 0
        self.generator_calls = 0
        self.reviewer_calls = 0

    def _model_field(self) -> dict[str, str]:
        model = self.behavior.response_model
        return {} if model is None else {"model": model}

    async def create(self, **kwargs: Any) -> Any:
        self.calls += 1
        failure = self.behavior.raise_on_call.get(self.calls)
        if failure is not None:
            raise failure
        node, role, version = classify(kwargs)
        payload = parse_payload(kwargs)
        if kwargs.get("stream"):
            self.generator_calls += 1
            return self._stream(kwargs, payload)
        if self.behavior.delay_seconds:
            await asyncio.sleep(self.behavior.delay_seconds)
        if node.endswith("_reviewer"):
            self.reviewer_calls += 1
            if self.reviewer_calls in self.behavior.invalid_review_calls:
                value: dict[str, Any] = {"unexpected": True}
            else:
                value = self._review(role or "tech", version or 1)
        elif node == "optimizer":
            value = self._plan(version or 1)
        elif node == "repair":
            kind = payload.get("kind")
            value = (
                self._review(role or "tech", 1) if kind == "review" else self._plan(1)
            )
        else:
            value = {}
        text = json.dumps(value, ensure_ascii=False)
        return {
            **self._model_field(),
            "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
            "usage": _usage(self.behavior, kwargs.get("messages"), text),
        }

    def _stream(self, kwargs: dict[str, Any], payload: dict[str, Any]) -> _FakeStream:
        text = fake_prd(payload)
        if self.generator_calls not in self.behavior.unfinished_generator_calls:
            text = f"{text}\n\n{PRD_COMPLETION_MARKER}"
        size = self.behavior.chunk_size
        pieces = [text[i : i + size] for i in range(0, len(text), size)]
        chunks: list[dict[str, Any]] = [
            {
                **self._model_field(),
                "choices": [{"delta": {"content": piece}, "finish_reason": None}],
            }
            for piece in pieces
        ]
        chunks.append(
            {
                **self._model_field(),
                "choices": [{"delta": {}, "finish_reason": "stop"}],
            }
        )
        chunks.append(
            {
                **self._model_field(),
                "choices": [],
                "usage": _usage(self.behavior, kwargs.get("messages"), text),
            }
        )
        return _FakeStream(chunks, self.behavior.delay_seconds)

    def _review(self, role: str, iteration: int) -> dict[str, Any]:
        score = self.behavior.review_scores.get(
            iteration, self.behavior.default_review_score
        )
        feedback: list[dict[str, str]] = []
        if iteration in self.behavior.must_fix_iterations:
            feedback.append(
                {
                    "severity": "must_fix",
                    "issue": f"模拟 {role} 评审：缺少异常流程。",
                    "recommendation": "补充异常流程。",
                }
            )
        return {
            "role": role,
            "score": score,
            "summary": f"模拟 {role} 评审，第 {iteration} 轮。",
            "strengths": ["结构清晰"],
            "feedback": feedback,
        }

    @staticmethod
    def _plan(iteration: int) -> dict[str, Any]:
        return {
            "iteration": iteration,
            "objective": "处理全部 must_fix 意见。",
            "items": [
                {
                    "source_role": "tech",
                    "source_roles": ["tech"],
                    "issue": "缺少异常流程。",
                    "required_change": "补充异常流程。",
                    "target_section": "功能需求",
                    "priority": "high",
                }
            ],
            "user_override": None,
        }
