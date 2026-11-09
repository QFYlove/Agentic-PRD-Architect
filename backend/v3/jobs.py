"""One execution unit per model task, with durable events for SSE replay.

A ``Job`` replaces the V2 run as the thing that executes. Each user action that
needs a model (one exploration round, one analysis, one outline, one generation
pass, one review, one optimisation) starts exactly one job; when it finishes
nothing else starts on its own.

The reliability rules are the V2 ones, reused rather than re-implemented:
``backend.failures`` decides what is retried (a truncation never is, a transient
transport failure once), how long to back off, and what the user is told.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from time import monotonic
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import ValidationError

from backend.config import Settings
from backend.errors import AppError, NodeTimeoutError, RetryableProviderError
from backend.failures import TRANSIENT_ATTEMPTS, backoff_seconds, classify, is_transient
from backend.observability import log_event, log_exception
from backend.prd_document import validate_generated_prd
from backend.providers.base import ProviderStructuredResult
from backend.schemas import TokenUsage
from backend.telemetry import estimate_cost
from backend.v3.llm import ModelGateway
from backend.v3.models import (
    TERMINAL_JOB_STATUSES,
    Job,
    JobError,
    JobEvent,
    JobKind,
    JobStatus,
    Project,
    Strict,
    Usage,
    now,
)
from backend.v3.prompts import REPAIR_SUFFIX
from backend.v3.store import ProjectStore

LOGGER = logging.getLogger("agentic_prd.v3.jobs")

S = TypeVar("S", bound=Strict)

#: Streamed live, never persisted: the finished section carries the full text.
TRANSIENT_EVENTS = frozenset({"section_delta"})
TERMINAL_EVENTS = frozenset({"job_succeeded", "job_failed", "job_cancelled"})
BUFFER_SIZE = 2000


class JobConflictError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "JOB_IN_PROGRESS",
            "This project already has an AI task running. Wait for it to finish.",
            409,
        )


class JobNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__("JOB_NOT_FOUND", "The requested job does not exist.", 404)


class JobContext:
    """What a job body may do: emit events and call the model safely."""

    def __init__(self, manager: JobManager, job: Job) -> None:
        self.manager = manager
        self.job = job
        self.gateway = manager.gateway

    async def emit(self, event: str, payload: dict[str, Any] | None = None) -> None:
        await self.manager.emit(self.job, event, payload or {})

    def _add_usage(self, usage: Any) -> None:
        current = self.job.usage
        self.job.usage = Usage(
            input_tokens=current.input_tokens + int(usage.input_tokens),
            output_tokens=current.output_tokens + int(usage.output_tokens),
            total_tokens=current.total_tokens + int(usage.total_tokens),
        )

    async def _timed(self, awaitable: Awaitable[Any], limit: float) -> Any:
        try:
            return await asyncio.wait_for(awaitable, timeout=limit)
        except TimeoutError as exc:
            raise NodeTimeoutError from exc

    async def structured(
        self,
        *,
        task: str,
        instructions: str,
        payload: dict[str, Any],
        schema: type[S],
    ) -> S:
        """Call, retry a transient failure once with backoff, repair once."""
        limit = self.manager.structured_timeout(self.job.kind)
        attempt = 0
        result: ProviderStructuredResult | None = None
        while True:
            attempt += 1
            self.job.attempts += 1
            try:
                result = await self._timed(
                    self.gateway.structured(
                        task=task,
                        instructions=instructions,
                        payload=payload,
                        schema=schema,
                        language=self.manager.language_of(self.job),
                    ),
                    limit,
                )
                break
            except Exception as exc:
                if not is_transient(exc) or attempt >= TRANSIENT_ATTEMPTS:
                    raise
                await self._retry_wait(task, exc, attempt)
        assert result is not None
        self._add_usage(result.usage)
        try:
            return schema.model_validate(result.value)
        except ValidationError as exc:
            log_event(
                LOGGER,
                "structured_output_repair",
                level=logging.WARNING,
                job_id=self.job.id,
                task=task,
                errors=exc.error_count(),
            )
            self.job.attempts += 1
            repaired = await self._timed(
                self.gateway.structured(
                    task=f"repair:{task}",
                    instructions=instructions + REPAIR_SUFFIX,
                    payload={
                        "invalid_value": result.value,
                        "validation_error": str(exc)[:4000],
                    },
                    schema=schema,
                    language=self.manager.language_of(self.job),
                ),
                limit,
            )
            self._add_usage(repaired.usage)
            return schema.model_validate(repaired.value)

    async def stream_text(
        self,
        *,
        task: str,
        instructions: str,
        payload: dict[str, Any],
        on_delta: Callable[[str], Awaitable[None]],
        on_reset: Callable[[], Awaitable[None]],
    ) -> str:
        """Stream one document part; validate completion like V2 generation."""
        attempt = 0
        while True:
            attempt += 1
            self.job.attempts += 1
            if attempt > 1:
                await on_reset()
            try:
                return await self._stream_once(task, instructions, payload, on_delta)
            except Exception as exc:
                if not is_transient(exc) or attempt >= TRANSIENT_ATTEMPTS:
                    raise
                await self._retry_wait(task, exc, attempt)

    async def _stream_once(
        self,
        task: str,
        instructions: str,
        payload: dict[str, Any],
        on_delta: Callable[[str], Awaitable[None]],
    ) -> str:
        iterator = self.gateway.stream(
            task=task,
            instructions=instructions,
            payload=payload,
            language=self.manager.language_of(self.job),
        ).__aiter__()
        deadline = monotonic() + self.manager.settings.generator_timeout_seconds
        content = ""
        buffer = ""
        finish_reason: str | None = None
        usage: Any | None = None
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise NodeTimeoutError
            try:
                event = await self._timed(iterator.__anext__(), remaining)
            except StopAsyncIteration:
                break
            if event.delta:
                content += event.delta
                buffer += event.delta
                if len(buffer) >= 96:
                    await on_delta(buffer)
                    buffer = ""
            if event.usage is not None:
                usage = event.usage
            if event.finish_reason:
                finish_reason = event.finish_reason
        if buffer:
            await on_delta(buffer)
        if usage is not None:
            self._add_usage(usage)
        validated = validate_generated_prd(content, finish_reason)
        if usage is None:
            raise RetryableProviderError("Provider omitted token usage")
        return validated

    async def _retry_wait(self, task: str, error: BaseException, attempt: int) -> None:
        log_event(
            LOGGER,
            "provider_retry",
            job_id=self.job.id,
            trace_id=self.job.trace_id,
            task=task,
            attempt=attempt + 1,
            reason=type(error).__name__,
        )
        delay = backoff_seconds(
            error, attempt, self.manager.settings.provider_retry_base_delay_seconds
        )
        if delay > 0:
            await asyncio.sleep(delay)


Runner = Callable[[JobContext], Awaitable[dict[str, Any]]]


class JobManager:
    def __init__(
        self,
        *,
        store: ProjectStore,
        gateway: ModelGateway,
        settings: Settings,
        heartbeat_seconds: float = 15,
    ) -> None:
        self.store = store
        self.gateway = gateway
        self.settings = settings
        self.heartbeat_seconds = heartbeat_seconds
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._buffers: dict[str, deque[JobEvent]] = {}
        self._conditions: dict[str, asyncio.Condition] = {}
        self._on_finish: dict[str, Callable[[Job], None]] = {}

    # --- configuration ------------------------------------------------------

    def structured_timeout(self, kind: JobKind) -> float:
        if kind is JobKind.REVIEW:
            return float(self.settings.reviewer_timeout_seconds)
        return float(self.settings.optimizer_timeout_seconds)

    def language_of(self, job: Job) -> str:
        project = self.store.get(Project, job.project_id)
        return project.language if project is not None else "zh"

    # --- lifecycle ----------------------------------------------------------

    def recover_interrupted(self) -> list[str]:
        """Fail jobs a previous process left running. Called once at start."""
        stale = self.store.select(
            Job, "status IN (?, ?)", (JobStatus.QUEUED.value, JobStatus.RUNNING.value)
        )
        for job in stale:
            job.status = JobStatus.FAILED
            job.error = JobError(
                code="JOB_INTERRUPTED",
                message="The backend restarted before the task finished.",
                retryable=True,
                category="interrupted",
                recovery_action="retry",
                trace_id=job.trace_id,
            )
            job.finished_at = now()
            job.latest_sequence += 1
            self.store.update(job)
            self.store.append_job_event(
                JobEvent(
                    job_id=job.id,
                    sequence=job.latest_sequence,
                    event="job_failed",
                    payload={"error": job.error.model_dump(mode="json")},
                    created_at=now(),
                )
            )
        return [job.id for job in stale]

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # --- queries ------------------------------------------------------------

    def get(self, job_id: str) -> Job:
        job = self.store.get(Job, job_id)
        if job is None:
            raise JobNotFoundError
        return job

    def active_for(self, project_id: str) -> Job | None:
        jobs = self.store.select(
            Job,
            "project_id = ? AND status IN (?, ?)",
            (project_id, JobStatus.QUEUED.value, JobStatus.RUNNING.value),
            order="created_at DESC",
        )
        return jobs[0] if jobs else None

    def list_for(self, project_id: str, limit: int = 50) -> list[Job]:
        return self.store.select(
            Job,
            "project_id = ?",
            (project_id,),
            order=f"created_at DESC LIMIT {int(limit)}",
        )

    # --- start / run ----------------------------------------------------------

    def start(
        self,
        *,
        project_id: str,
        kind: JobKind,
        input: dict[str, Any],
        runner: Runner,
        on_finish: Callable[[Job], None] | None = None,
    ) -> Job:
        if self.active_for(project_id) is not None:
            raise JobConflictError
        job = Job(
            id=uuid4().hex,
            project_id=project_id,
            kind=kind,
            status=JobStatus.QUEUED,
            input=input,
            provider=self.gateway.provider_name,
            model=self.gateway.model,
            trace_id=uuid4().hex[:16],
            created_at=now(),
        )
        self.store.insert(job)
        self._buffers[job.id] = deque(maxlen=BUFFER_SIZE)
        self._conditions[job.id] = asyncio.Condition()
        if on_finish is not None:
            self._on_finish[job.id] = on_finish
        self._tasks[job.id] = asyncio.create_task(self._run(job, runner))
        return job

    async def _run(self, job: Job, runner: Runner) -> None:
        context = JobContext(self, job)
        job.status = JobStatus.RUNNING
        job.started_at = now()
        self.store.update(job)
        await self.emit(job, "job_started", {"kind": job.kind.value})
        log_event(
            LOGGER,
            "job_started",
            job_id=job.id,
            project_id=job.project_id,
            kind=job.kind,
            trace_id=job.trace_id,
        )
        try:
            job.result = await runner(context)
            job.status = JobStatus.SUCCEEDED
            event, payload = "job_succeeded", {"result": job.result}
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
            event, payload = "job_cancelled", {}
        except Exception as exc:
            info = classify(exc, has_best_version=False)
            job.status = JobStatus.FAILED
            job.error = JobError(
                code=info.code,
                message=info.message,
                retryable=info.retryable,
                category=info.category.value,
                recovery_action=info.recovery_action.value,
                trace_id=job.trace_id,
            )
            event, payload = "job_failed", {"error": job.error.model_dump(mode="json")}
            log_exception(
                LOGGER,
                "job_failed",
                exc,
                job_id=job.id,
                kind=job.kind,
                trace_id=job.trace_id,
                code=info.code,
            )
        job.finished_at = now()
        job.cost = estimate_cost(
            _as_token_usage(job.usage), self.settings, is_mock=self.gateway.is_mock
        )
        callback = self._on_finish.pop(job.id, None)
        if callback is not None:
            try:
                callback(job)
            except Exception as exc:  # pragma: no cover - defensive
                log_exception(LOGGER, "job_finish_hook_failed", exc, job_id=job.id)
        self.store.update(job)
        await self.emit(job, event, payload)
        self._tasks.pop(job.id, None)
        log_event(
            LOGGER,
            "job_finished",
            job_id=job.id,
            kind=job.kind,
            status=job.status,
            trace_id=job.trace_id,
            input_tokens=job.usage.input_tokens,
            output_tokens=job.usage.output_tokens,
        )

    async def cancel(self, job_id: str) -> Job:
        self.get(job_id)
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return self.get(job_id)

    async def wait(self, job_id: str, seconds: float = 10) -> Job:
        task = self._tasks.get(job_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout=seconds)
        return self.get(job_id)

    # --- events -------------------------------------------------------------

    async def emit(self, job: Job, event: str, payload: dict[str, Any]) -> None:
        job.latest_sequence += 1
        envelope = JobEvent(
            job_id=job.id,
            sequence=job.latest_sequence,
            event=event,
            payload=payload,
            created_at=now(),
        )
        if event not in TRANSIENT_EVENTS:
            self.store.append_job_event(envelope)
            self.store.update(job)
        buffer = self._buffers.get(job.id)
        condition = self._conditions.get(job.id)
        if buffer is not None and condition is not None:
            async with condition:
                buffer.append(envelope)
                condition.notify_all()

    def replay(self, job_id: str, after_sequence: int) -> list[JobEvent]:
        buffer = self._buffers.get(job_id)
        if buffer and after_sequence >= buffer[0].sequence - 1:
            return [event for event in buffer if event.sequence > after_sequence]
        return self.store.job_events(job_id, after_sequence)

    async def subscribe(
        self, job_id: str, after_sequence: int = 0
    ) -> AsyncIterator[JobEvent | None]:
        """Replay what was missed, then follow live until the job ends.

        ``None`` is a heartbeat. Sequence numbers order events but may skip the
        transient deltas when they were replayed from the database.
        """
        self.get(job_id)
        cursor = after_sequence
        while True:
            pending = self.replay(job_id, cursor)
            for event in pending:
                cursor = event.sequence
                yield event
                if event.event in TERMINAL_EVENTS:
                    return
            if pending:
                continue
            job = self.get(job_id)
            if job.status in TERMINAL_JOB_STATUSES and job.id not in self._tasks:
                return
            condition = self._conditions.get(job_id)
            if condition is None:
                return
            heartbeat = False
            async with condition:
                if self.replay(job_id, cursor):
                    continue
                try:
                    await asyncio.wait_for(
                        condition.wait(), timeout=self.heartbeat_seconds
                    )
                except TimeoutError:
                    heartbeat = True
            if heartbeat:
                yield None


def _as_token_usage(usage: Usage) -> TokenUsage:
    return TokenUsage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.total_tokens,
    )
