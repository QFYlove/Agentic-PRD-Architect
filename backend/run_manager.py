from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from time import monotonic
from typing import Any, Protocol
from uuid import UUID, uuid4

from backend.config import Settings
from backend.errors import RunCapacityError, RunConflictError
from backend.event_store import EventStore
from backend.observability import log_event
from backend.providers.base import LLMProvider
from backend.run_store import InMemoryRunStore
from backend.schemas import (
    CreateRunRequest,
    NodeStatus,
    PRDVersion,
    ResumeRunRequest,
    RunEvent,
    RunEventType,
    RunSnapshot,
    RunStatus,
    RunSummary,
    TokenUsage,
    utc_now,
)
from backend.state_machine import TERMINAL_RUN_STATUSES, require_transition
from backend.telemetry import add_usage, estimate_cost


class WorkflowRunner(Protocol):
    async def run(self, run_id: UUID) -> None: ...


Mutation = Callable[[RunSnapshot], None]
LOGGER = logging.getLogger("agentic_prd.workflow")


class RunManager:
    def __init__(
        self,
        *,
        settings: Settings,
        provider: LLMProvider,
        run_store: InMemoryRunStore,
        event_store: EventStore,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.run_store = run_store
        self.event_store = event_store
        self.workflow: WorkflowRunner | None = None
        self.tasks: dict[UUID, asyncio.Task[None]] = {}
        self.cancel_signals: dict[UUID, asyncio.Event] = {}
        self.resume_signals: dict[UUID, asyncio.Event] = {}
        self._active_started: dict[UUID, float] = {}
        self._paused_started: dict[UUID, float] = {}
        self._paused_total: dict[UUID, float] = {}
        self._node_started: dict[tuple[UUID, str], float] = {}
        self._cleanup_task: asyncio.Task[None] | None = None
        self._accepting = True
        self._create_lock = asyncio.Lock()
        self._task_lock = asyncio.Lock()

    def set_workflow(self, workflow: WorkflowRunner) -> None:
        self.workflow = workflow

    async def start(self) -> None:
        self._accepting = True
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_loop(),
                name="run-store-cleanup",
            )

    async def shutdown(self) -> None:
        self._accepting = False
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            await asyncio.gather(self._cleanup_task, return_exceptions=True)
            self._cleanup_task = None
        for signal in self.cancel_signals.values():
            signal.set()
        for signal in self.resume_signals.values():
            signal.set()
        for run_id in await self.run_store.run_ids():
            await self.event_store.wake(run_id)
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        await self.run_store.close()
        self.event_store.close()

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.cleanup_interval_seconds)
            await self.cleanup_once()

    async def cleanup_once(self) -> list[UUID]:
        expired = await self.run_store.cleanup_expired()
        for run_id in expired:
            self.event_store.remove_run(run_id)
            self.cancel_signals.pop(run_id, None)
            self.resume_signals.pop(run_id, None)
            self._active_started.pop(run_id, None)
            self._paused_started.pop(run_id, None)
            self._paused_total.pop(run_id, None)
            for key in [key for key in self._node_started if key[0] == run_id]:
                self._node_started.pop(key, None)
            self.tasks.pop(run_id, None)
            log_event(LOGGER, "run_resources_cleaned", run_id=run_id)
        return expired

    async def create_run(self, request: CreateRunRequest) -> RunSnapshot:
        if not self._accepting:
            raise RunConflictError("APP_SHUTTING_DOWN", "The application is stopping.")
        async with self._create_lock:
            if await self.run_store.active_count() >= self.settings.max_concurrent_runs:
                raise RunCapacityError
            run_id = uuid4()
            now = utc_now()
            snapshot = RunSnapshot(
                run_id=run_id,
                user_idea=request.user_idea,
                target_audience=request.target_audience,
                user_constraints=request.user_constraints,
                max_iterations=request.max_iterations,
                quality_threshold=request.quality_threshold,
                node_statuses={
                    "generator": NodeStatus.PENDING,
                    "tech_reviewer": NodeStatus.PENDING,
                    "ux_reviewer": NodeStatus.PENDING,
                    "biz_reviewer": NodeStatus.PENDING,
                    "aggregator": NodeStatus.PENDING,
                    "optimizer": NodeStatus.PENDING,
                },
                is_mock=self.provider.is_mock,
                cost_available=self.provider.is_mock or self.settings.has_model_pricing,
                created_at=now,
                updated_at=now,
            )
            await self.run_store.create(snapshot)
            self.event_store.create_run(run_id)
            self.cancel_signals[run_id] = asyncio.Event()
            self.resume_signals[run_id] = asyncio.Event()
            self._active_started[run_id] = monotonic()
            self._paused_total[run_id] = 0.0
            await self.start_run(run_id)
        log_event(
            LOGGER,
            "run_accepted",
            run_id=run_id,
            provider=type(self.provider).__name__,
            mock=self.provider.is_mock,
        )
        return snapshot.model_copy(deep=True)

    async def start_run(self, run_id: UUID) -> None:
        if self.workflow is None:
            raise RuntimeError("Workflow has not been configured")
        async with self._task_lock:
            existing = self.tasks.get(run_id)
            if existing is not None and not existing.done():
                raise RunConflictError(
                    "RUN_ALREADY_STARTED",
                    "The run already has an active workflow.",
                )
            task = asyncio.create_task(
                self._run_workflow(run_id),
                name=f"run-{run_id}",
            )
            self.tasks[run_id] = task

    async def _run_workflow(self, run_id: UUID) -> None:
        assert self.workflow is not None
        started = monotonic()
        log_event(LOGGER, "run_started", run_id=run_id)
        try:
            await self.workflow.run(run_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            if self.is_cancel_requested(run_id):
                await self.finalize_cancel(run_id)
            else:
                await self.fail_run(
                    run_id,
                    code="WORKFLOW_FAILED",
                    message="The workflow could not complete.",
                    retryable=False,
                )
        finally:
            snapshot = await self.get_run(run_id)
            log_event(
                LOGGER,
                "run_finished",
                run_id=run_id,
                status=snapshot.status,
                duration_ms=round((monotonic() - started) * 1000, 2),
            )
            async with self._task_lock:
                current = self.tasks.get(run_id)
                if current is asyncio.current_task():
                    self.tasks.pop(run_id, None)

    async def wait_for_completion(
        self,
        run_id: UUID,
        *,
        wait_seconds: float = 10,
    ) -> RunSnapshot:
        task = self.tasks.get(run_id)
        if task is not None:
            await asyncio.wait_for(asyncio.shield(task), timeout=wait_seconds)
        return await self.get_run(run_id)

    async def get_run(self, run_id: UUID) -> RunSnapshot:
        return await self.run_store.get(run_id)

    async def list_runs(self, *, limit: int) -> list[RunSummary]:
        return await self.run_store.list_runs(limit=limit)

    async def commit(
        self,
        run_id: UUID,
        mutation: Mutation,
        *,
        event: RunEventType | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunSnapshot:
        lock = self.run_store.lock_for(run_id)
        async with lock:
            state = self.run_store.get_unlocked(run_id)
            previous_nodes = dict(state.node_statuses)
            mutation(state)
            state.updated_at = utc_now()
            state.elapsed_seconds = self.active_elapsed(run_id)
            if event is not None:
                envelope = await self.event_store.append(
                    run_id=run_id,
                    event=event,
                    iteration=state.current_iteration,
                    payload=payload or {},
                )
                state.latest_event_sequence = envelope.sequence
            await self.run_store.save_unlocked(run_id)
            for node, node_status in state.node_statuses.items():
                if (
                    node_status
                    in {NodeStatus.SUCCEEDED, NodeStatus.FAILED, NodeStatus.SKIPPED}
                    and previous_nodes.get(node) is not node_status
                ):
                    started = self._node_started.pop((run_id, node), None)
                    log_event(
                        LOGGER,
                        "node_finished",
                        run_id=run_id,
                        node=node,
                        status=node_status,
                        duration_ms=(
                            round((monotonic() - started) * 1000, 2)
                            if started is not None
                            else None
                        ),
                    )
            return state.model_copy(deep=True)

    async def transition(
        self,
        run_id: UUID,
        target: RunStatus,
        *,
        event: RunEventType = RunEventType.STATUS_CHANGED,
        payload: dict[str, Any] | None = None,
    ) -> RunSnapshot:
        lock = self.run_store.lock_for(run_id)
        async with lock:
            state = self.run_store.get_unlocked(run_id)
            previous = state.status
            require_transition(previous, target)
            state.status = target
            if target in TERMINAL_RUN_STATUSES:
                state.completed_at = utc_now()
                state.active_node = None
            state.updated_at = utc_now()
            state.elapsed_seconds = self.active_elapsed(run_id)
            event_payload = {
                "previous": previous.value,
                "current": target.value,
            }
            if payload:
                event_payload.update(payload)
            envelope = await self.event_store.append(
                run_id=run_id,
                event=event,
                iteration=state.current_iteration,
                payload=event_payload,
            )
            state.latest_event_sequence = envelope.sequence
            await self.run_store.save_unlocked(run_id)
            return state.model_copy(deep=True)

    async def set_stage(self, run_id: UUID, target: RunStatus) -> RunSnapshot:
        state = await self.get_run(run_id)
        if state.status in {
            RunStatus.PAUSE_REQUESTED,
            RunStatus.CANCEL_REQUESTED,
        }:
            return state
        if state.status == target:
            return state
        return await self.transition(run_id, target)

    async def request_pause(self, run_id: UUID) -> RunSnapshot:
        state = await self.get_run(run_id)
        if state.status in TERMINAL_RUN_STATUSES:
            raise RunConflictError(
                "RUN_TERMINAL",
                "A terminal run cannot be paused.",
            )
        if state.status in {RunStatus.PAUSE_REQUESTED, RunStatus.PAUSED}:
            return state
        if state.status not in {
            RunStatus.GENERATING,
            RunStatus.REVIEWING,
            RunStatus.AGGREGATING,
            RunStatus.OPTIMIZING,
        }:
            raise RunConflictError(
                "RUN_NOT_PAUSABLE",
                "The run cannot be paused in its current state.",
            )
        return await self.transition(
            run_id,
            RunStatus.PAUSE_REQUESTED,
            event=RunEventType.PAUSE_REQUESTED,
            payload={"safe_point": "after_aggregation"},
        )

    async def enter_paused(self, run_id: UUID) -> RunSnapshot:
        snapshot = await self.transition(
            run_id,
            RunStatus.PAUSED,
            event=RunEventType.RUN_PAUSED,
            payload={"iteration": (await self.get_run(run_id)).current_iteration},
        )
        self._paused_started[run_id] = monotonic()
        self.resume_signals[run_id].clear()
        return snapshot

    async def resume_run(
        self,
        run_id: UUID,
        request: ResumeRunRequest,
    ) -> RunSnapshot:
        state = await self.get_run(run_id)
        if state.status is not RunStatus.PAUSED:
            raise RunConflictError(
                "RUN_NOT_PAUSED",
                "Only a paused run can be resumed.",
            )
        paused_at = self._paused_started.pop(run_id, None)
        if paused_at is not None:
            self._paused_total[run_id] += monotonic() - paused_at

        def mutate(snapshot: RunSnapshot) -> None:
            require_transition(snapshot.status, RunStatus.OPTIMIZING)
            snapshot.status = RunStatus.OPTIMIZING
            snapshot.pending_user_override = request.user_override

        result = await self.commit(
            run_id,
            mutate,
            event=RunEventType.RUN_RESUMED,
            payload={"has_user_override": bool(request.user_override)},
        )
        self.resume_signals[run_id].set()
        return result

    async def cancel_run(self, run_id: UUID) -> RunSnapshot:
        state = await self.get_run(run_id)
        if state.status is RunStatus.CANCELLED:
            return state
        if state.status in {
            RunStatus.COMPLETED,
            RunStatus.MAX_ITERATIONS_REACHED,
            RunStatus.FAILED,
        }:
            raise RunConflictError(
                "RUN_TERMINAL",
                "A completed or failed run cannot be cancelled.",
            )
        if state.status is not RunStatus.CANCEL_REQUESTED:
            await self.transition(run_id, RunStatus.CANCEL_REQUESTED)
        self.cancel_signals[run_id].set()
        self.resume_signals[run_id].set()
        return await self.finalize_cancel(run_id)

    async def finalize_cancel(self, run_id: UUID) -> RunSnapshot:
        state = await self.get_run(run_id)
        if state.status is RunStatus.CANCELLED:
            return state
        if state.status is not RunStatus.CANCEL_REQUESTED:
            return state
        result = await self.transition(
            run_id,
            RunStatus.CANCELLED,
            event=RunEventType.RUN_CANCELLED,
            payload={"reason": "user_requested"},
        )
        await self.event_store.wake(run_id)
        return result

    async def fail_run(
        self,
        run_id: UUID,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> RunSnapshot:
        from backend.schemas import RunError

        state = await self.get_run(run_id)
        if state.status in TERMINAL_RUN_STATUSES:
            return state

        def mutate(snapshot: RunSnapshot) -> None:
            snapshot.status = RunStatus.FAILED
            if snapshot.active_node is not None:
                snapshot.node_statuses[snapshot.active_node] = NodeStatus.FAILED
            snapshot.error = RunError(
                code=code,
                message=message[:2000],
                retryable=retryable,
            )
            snapshot.completed_at = utc_now()
            snapshot.active_node = None

        result = await self.commit(
            run_id,
            mutate,
            event=RunEventType.RUN_FAILED,
            payload={"error_code": code, "message": message, "retryable": retryable},
        )
        await self.event_store.wake(run_id)
        return result

    async def record_usage(
        self,
        run_id: UUID,
        *,
        node: str,
        usage: TokenUsage,
    ) -> RunSnapshot:
        event_payload: dict[str, Any] = {}

        def mutate(state: RunSnapshot) -> None:
            previous = state.node_tokens.get(node, TokenUsage())
            state.node_tokens[node] = add_usage(previous, usage)
            state.total_tokens = add_usage(state.total_tokens, usage)
            state.estimated_cost_usd = estimate_cost(
                state.total_tokens,
                self.settings,
                is_mock=self.provider.is_mock,
            )
            state.cost_available = (
                self.provider.is_mock or state.estimated_cost_usd is not None
            )
            event_payload.update(
                {
                    "tokens": state.total_tokens.model_dump(mode="json"),
                    "cost": state.estimated_cost_usd,
                    "cost_available": state.cost_available,
                    "mock": state.is_mock,
                    "elapsed": state.elapsed_seconds,
                }
            )

        return await self.commit(
            run_id,
            mutate,
            event=RunEventType.TELEMETRY_UPDATED,
            payload=event_payload,
        )

    async def append_version(
        self,
        run_id: UUID,
        version: PRDVersion,
    ) -> RunSnapshot:
        def mutate(state: RunSnapshot) -> None:
            if any(item.version == version.version for item in state.versions):
                raise RunConflictError(
                    "VERSION_EXISTS",
                    "The PRD version already exists.",
                )
            state.versions.append(version)
            state.current_prd = version.content

        return await self.commit(run_id, mutate)

    async def stream_events(
        self,
        run_id: UUID,
        *,
        after_sequence: int,
    ) -> AsyncIterator[RunEvent | None]:
        async def is_terminal() -> bool:
            return (
                not self._accepting
                or (await self.get_run(run_id)).status in TERMINAL_RUN_STATUSES
            )

        async for event in self.event_store.subscribe(
            run_id,
            after_sequence=after_sequence,
            is_terminal=is_terminal,
        ):
            yield event

    def is_cancel_requested(self, run_id: UUID) -> bool:
        return self.cancel_signals[run_id].is_set()

    async def wait_until_resumed_or_cancelled(self, run_id: UUID) -> None:
        resume_wait = asyncio.create_task(self.resume_signals[run_id].wait())
        cancel_wait = asyncio.create_task(self.cancel_signals[run_id].wait())
        done, pending = await asyncio.wait(
            {resume_wait, cancel_wait},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)

    def active_elapsed(self, run_id: UUID) -> float:
        started = self._active_started.get(run_id)
        if started is None:
            return 0.0
        paused = self._paused_total.get(run_id, 0.0)
        paused_at = self._paused_started.get(run_id)
        if paused_at is not None:
            paused += monotonic() - paused_at
        return max(0.0, monotonic() - started - paused)

    def remaining_run_seconds(self, run_id: UUID) -> float:
        return max(0.0, self.settings.run_timeout_seconds - self.active_elapsed(run_id))

    async def mark_node(
        self,
        run_id: UUID,
        node: str,
        status: NodeStatus,
        *,
        event: bool = False,
        role: str | None = None,
    ) -> RunSnapshot:
        def mutate(state: RunSnapshot) -> None:
            state.node_statuses[node] = status
            state.active_node = (
                node if status is NodeStatus.RUNNING else state.active_node
            )
            if status in {NodeStatus.SUCCEEDED, NodeStatus.FAILED, NodeStatus.SKIPPED}:
                if state.active_node == node:
                    state.active_node = None

        result = await self.commit(
            run_id,
            mutate,
            event=RunEventType.NODE_STARTED if event else None,
            payload={"node": node, "role": role} if event else None,
        )
        key = (run_id, node)
        if status is NodeStatus.RUNNING:
            self._node_started[key] = monotonic()
            log_event(
                LOGGER,
                "node_started",
                run_id=run_id,
                node=node,
                role=role,
                provider=type(self.provider).__name__,
            )
        return result
