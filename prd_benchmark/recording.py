"""SDK-level call recording for every model request the harness makes.

The product's provider reads the response ``model`` with a fallback to its own
configured id (``backend/providers/compatible.py``), so a missing field and an
echoed alias look identical one layer up. The recorder therefore wraps the
OpenAI-compatible *client* that ``OpenAICompatibleLLMProvider`` accepts through
its ``client=`` argument and reads the raw chunks and responses itself.

It never sees an API key: it wraps an already-constructed client.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from prd_benchmark.guard import CallGuard, Reservation

_PAYLOAD = re.compile(r"<user_input_json>\n(.*)\n</user_input_json>", re.DOTALL)
_REPAIR_TASK = "Repair the invalid structured result exactly once."


class BudgetExceededError(RuntimeError):
    """Raised before a call that would start after the token cap was reached."""


@dataclass
class TokenBudget:
    limit: int | None
    used: int = 0

    def check(self) -> None:
        if self.limit is not None and self.used >= self.limit:
            raise BudgetExceededError(
                f"token budget exhausted: {self.used} >= {self.limit}"
            )

    def add(self, tokens: int | None) -> None:
        if tokens:
            self.used += tokens


@dataclass
class CallContext:
    batch_id: str
    case_id: str
    condition: str


@dataclass
class CallRecord:
    batch_id: str
    case_id: str
    condition: str
    call_index: int
    node: str
    role: str | None
    version: int | None
    attempt: int
    configured_model: str | None
    request_sha256: str
    stream: bool
    started_at: str
    ended_at: str | None = None
    wall_seconds: float | None = None
    first_token_seconds: float | None = None
    response_model: str | None = None
    response_model_missing: bool = True
    response_models_seen: list[str] = field(default_factory=list)
    http_status: int | None = None
    outcome: str = "pending"
    error_class: str | None = None
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cache_hit_tokens: int | None = None
    cache_miss_tokens: int | None = None
    reasoning_tokens: int | None = None
    usage_raw_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        dumped = dump()
        if isinstance(dumped, dict):
            return dumped
    try:
        attributes = vars(value)
    except TypeError:
        return {}
    return {k: v for k, v in attributes.items() if not k.startswith("_")}


def _int(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def request_sha256(kwargs: dict[str, Any]) -> str:
    """Hash of everything that shapes the model's answer (timeout excluded)."""
    material = {k: v for k, v in kwargs.items() if k != "timeout"}
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def parse_payload(kwargs: dict[str, Any]) -> dict[str, Any]:
    """The product's ``<user_input_json>`` payload from a request, or ``{}``."""
    messages = kwargs.get("messages") or []
    for message in messages:
        if _get(message, "role") == "user":
            match = _PAYLOAD.search(str(_get(message, "content") or ""))
            if match:
                try:
                    parsed = json.loads(match.group(1))
                except json.JSONDecodeError:
                    return {}
                return parsed if isinstance(parsed, dict) else {}
    return {}


def classify(kwargs: dict[str, Any]) -> tuple[str, str | None, int | None]:
    """(node, role, version) for one request, read from the product payload."""
    payload = parse_payload(kwargs)
    iteration = payload.get("iteration")
    version = iteration if isinstance(iteration, int) else None
    role = payload.get("required_role")
    role = role if isinstance(role, str) else None
    if kwargs.get("stream"):
        return "generator", None, version
    if payload.get("task") == _REPAIR_TASK:
        return "repair", role, None
    if "evaluation" in payload:
        return "optimizer", None, version
    if role is not None and "prd" in payload:
        return f"{role}_reviewer", role, version
    return "unknown", role, version


#: The provider's documented maximum output; reserved when a request sends no
#: ``max_tokens`` (the product always sends one).
DEEPSEEK_MAX_OUTPUT_TOKENS = 384_000


def _reservation_text(kwargs: dict[str, Any]) -> str:
    """Everything the request sends that is billed as input."""
    material = {k: v for k, v in kwargs.items() if k not in {"timeout", "stream"}}
    return json.dumps(material, ensure_ascii=False, default=str)


def usage_breakdown(record: CallRecord) -> Any:
    """Reported usage as a ``UsageBreakdown``; missing cache split = all miss."""
    from prd_benchmark.pricing import UsageBreakdown

    if record.input_tokens is None or record.output_tokens is None:
        return UsageBreakdown()
    hit = record.cache_hit_tokens or 0
    miss = (
        record.cache_miss_tokens
        if record.cache_miss_tokens is not None
        else max(record.input_tokens - hit, 0)
    )
    return UsageBreakdown(
        input_cache_miss=miss, input_cache_hit=hit, output=record.output_tokens
    )


class _Completions:
    def __init__(self, owner: RecordingClient) -> None:
        self._owner = owner

    async def create(self, **kwargs: Any) -> Any:
        return await self._owner.create(**kwargs)


class _Chat:
    def __init__(self, owner: RecordingClient) -> None:
        self.completions = _Completions(owner)


class RecordingClient:
    """Duck-typed stand-in for ``AsyncOpenAI`` that records each request."""

    def __init__(
        self,
        inner: Any,
        *,
        context: CallContext,
        budget: TokenBudget | None = None,
        guard: CallGuard | None = None,
        max_output_fallback: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self.context = context
        self.budget = budget
        self.guard = guard
        self.max_output_fallback = max_output_fallback or DEEPSEEK_MAX_OUTPUT_TOKENS
        self._reservations: dict[int, Reservation] = {}
        self._clock = clock
        self.records: list[CallRecord] = []
        self._attempts: dict[tuple[str, str | None, int | None], int] = {}
        self._last_version: int | None = None
        self.chat = _Chat(self)

    def _start(self, kwargs: dict[str, Any]) -> tuple[CallRecord, float]:
        node, role, version = classify(kwargs)
        if node == "repair":
            version = self._last_version
        elif version is not None:
            self._last_version = version
        key = (node, role, version)
        self._attempts[key] = self._attempts.get(key, 0) + 1
        record = CallRecord(
            batch_id=self.context.batch_id,
            case_id=self.context.case_id,
            condition=self.context.condition,
            call_index=len(self.records) + 1,
            node=node,
            role=role,
            version=version,
            attempt=self._attempts[key],
            configured_model=kwargs.get("model"),
            request_sha256=request_sha256(kwargs),
            stream=bool(kwargs.get("stream")),
            started_at=_now(),
        )
        self.records.append(record)
        return record, self._clock()

    def _finish(
        self,
        record: CallRecord,
        started: float,
        outcome: str,
        error: BaseException | None = None,
    ) -> None:
        if record.outcome != "pending":
            return
        record.outcome = outcome
        record.ended_at = _now()
        record.wall_seconds = round(self._clock() - started, 3)
        if error is not None:
            record.error_class = type(error).__name__
            status = getattr(error, "status_code", None)
            record.http_status = status if isinstance(status, int) else None
        elif outcome == "ok":
            record.http_status = 200
        if self.budget is not None:
            self.budget.add(record.total_tokens)
        reservation = self._reservations.pop(record.call_index, None)
        if self.guard is not None and reservation is not None:
            from prd_benchmark.guard import StopBatchError

            try:
                self.guard.after_call(
                    reservation,
                    usage=usage_breakdown(record) if outcome == "ok" else None,
                    at=datetime.fromisoformat(record.started_at),
                    # The product enforces its timeouts by cancelling the call.
                    timed_out=outcome in {"timeout", "cancelled"},
                    models=record.response_models_seen if outcome == "ok" else None,
                    note=outcome,
                )
            except StopBatchError:
                # Latched in the monitor: the call already happened and its
                # result is kept; the *next* before_call refuses.
                pass

    def observe_model(self, record: CallRecord, value: Any) -> None:
        model = _get(value, "model")
        if isinstance(model, str) and model:
            if record.response_model is None:
                record.response_model = model
                record.response_model_missing = False
            if model not in record.response_models_seen:
                record.response_models_seen.append(model)

    @staticmethod
    def observe_usage(record: CallRecord, usage: Any) -> None:
        raw = _as_dict(usage)
        if not raw:
            return
        record.usage_raw_keys = sorted(raw)
        record.input_tokens = _int(raw.get("prompt_tokens", raw.get("input_tokens")))
        record.output_tokens = _int(
            raw.get("completion_tokens", raw.get("output_tokens"))
        )
        record.total_tokens = _int(raw.get("total_tokens"))
        prompt_details = _as_dict(raw.get("prompt_tokens_details"))
        completion_details = _as_dict(raw.get("completion_tokens_details"))
        record.cache_hit_tokens = _int(
            raw.get("prompt_cache_hit_tokens", prompt_details.get("cached_tokens"))
        )
        record.cache_miss_tokens = _int(raw.get("prompt_cache_miss_tokens"))
        record.reasoning_tokens = _int(completion_details.get("reasoning_tokens"))

    async def create(self, **kwargs: Any) -> Any:
        if self.budget is not None:
            self.budget.check()
        reservation = None
        if self.guard is not None:
            node, _, version = classify(kwargs)
            max_out = kwargs.get("max_tokens")
            reservation = self.guard.before_call(
                "generator",
                f"{self.context.case_id}/{self.context.condition}/{node}/v{version}",
                _reservation_text(kwargs),
                int(max_out) if isinstance(max_out, int) else self.max_output_fallback,
            )
        record, started = self._start(kwargs)
        if reservation is not None:
            self._reservations[record.call_index] = reservation
        try:
            result = await self._inner.chat.completions.create(**kwargs)
        except asyncio.CancelledError as error:
            self._finish(record, started, "cancelled", error)
            raise
        except Exception as error:
            outcome = "timeout" if "Timeout" in type(error).__name__ else "error"
            self._finish(record, started, outcome, error)
            raise
        if record.stream:
            return _RecordingStream(self, record, started, result)
        self.observe_model(record, result)
        self.observe_usage(record, _get(result, "usage"))
        choices = _get(result, "choices") or []
        if choices:
            reason = _get(choices[0], "finish_reason")
            record.finish_reason = str(reason) if reason is not None else None
        self._finish(record, started, "ok")
        return result

    def records_as_dicts(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self.records]


class _RecordingStream:
    """Async-iterable wrapper over a streamed completion."""

    def __init__(
        self,
        owner: RecordingClient,
        record: CallRecord,
        started: float,
        inner: Any,
    ) -> None:
        self._owner = owner
        self._record = record
        self._started = started
        self._inner = inner
        self._iterator: Any = None

    def __aiter__(self) -> _RecordingStream:
        return self

    async def __anext__(self) -> Any:
        if self._iterator is None:
            self._iterator = self._inner.__aiter__()
        try:
            chunk = await self._iterator.__anext__()
        except StopAsyncIteration:
            self._owner._finish(self._record, self._started, "ok")
            raise
        except asyncio.CancelledError as error:
            self._owner._finish(self._record, self._started, "cancelled", error)
            raise
        except Exception as error:
            outcome = "timeout" if "Timeout" in type(error).__name__ else "error"
            self._owner._finish(self._record, self._started, outcome, error)
            raise
        self._observe(chunk)
        return chunk

    def _observe(self, chunk: Any) -> None:
        record = self._record
        self._owner.observe_model(record, chunk)
        for choice in _get(chunk, "choices") or []:
            reason = _get(choice, "finish_reason")
            if reason:
                record.finish_reason = str(reason)
            delta = _get(_get(choice, "delta"), "content")
            if delta and record.first_token_seconds is None:
                elapsed = self._owner._clock() - self._started
                record.first_token_seconds = round(elapsed, 3)
        usage = _get(chunk, "usage")
        if usage is not None:
            self._owner.observe_usage(record, usage)

    async def close(self) -> None:
        # Closed before the stream finished: the caller abandoned it.
        self._owner._finish(self._record, self._started, "abandoned")
        close = getattr(self._inner, "close", None) or getattr(
            self._inner, "aclose", None
        )
        if close is not None:
            result = close()
            if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
                await result
