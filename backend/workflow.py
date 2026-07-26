from __future__ import annotations

import asyncio
import logging
import warnings
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any, TypedDict, TypeVar
from uuid import UUID

from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
from pydantic import ValidationError

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore",
        message="The default value of `allowed_objects` will change.*",
        category=LangChainPendingDeprecationWarning,
    )
    from langgraph.graph import END, START, StateGraph

from backend.errors import (
    InvalidModelError,
    ProviderAuthenticationError,
    RetryableProviderError,
)
from backend.observability import log_event
from backend.providers.base import ProviderStructuredResult
from backend.run_manager import RunManager
from backend.schemas import (
    EvaluationResult,
    NodeStatus,
    PRDVersion,
    ReviewRole,
    RevisionPlan,
    RoleReview,
    RunEventType,
    RunSnapshot,
    RunStatus,
    TokenUsage,
    utc_now,
)
from backend.state_machine import TERMINAL_RUN_STATUSES

T = TypeVar("T")
LOGGER = logging.getLogger("agentic_prd.workflow")


class WorkflowState(TypedDict):
    run_id: UUID


class WorkflowCancelled(Exception):
    pass


class AgentWorkflow:
    def __init__(self, manager: RunManager) -> None:
        self.manager = manager
        graph = StateGraph(WorkflowState)
        graph.add_node("generator", self._generator_node)  # type: ignore[call-overload]
        graph.add_node(  # type: ignore[call-overload]
            "tech_reviewer", self._tech_reviewer_node
        )
        graph.add_node(  # type: ignore[call-overload]
            "ux_reviewer", self._ux_reviewer_node
        )
        graph.add_node(  # type: ignore[call-overload]
            "biz_reviewer", self._biz_reviewer_node
        )
        graph.add_node("aggregator", self._aggregator_node)  # type: ignore[call-overload]
        graph.add_node("optimizer", self._optimizer_node)  # type: ignore[call-overload]
        graph.add_edge(START, "generator")
        graph.add_edge("generator", "tech_reviewer")
        graph.add_edge("generator", "ux_reviewer")
        graph.add_edge("generator", "biz_reviewer")
        graph.add_edge(
            ["tech_reviewer", "ux_reviewer", "biz_reviewer"],
            "aggregator",
        )
        graph.add_conditional_edges(
            "aggregator",
            self._route_after_aggregate,
            {"optimizer": "optimizer", "end": END},
        )
        graph.add_edge("optimizer", "generator")
        self.graph = graph.compile()

    async def run(self, run_id: UUID) -> None:
        try:
            await self.manager.commit(
                run_id,
                lambda state: setattr(state, "started_at", utc_now()),
                event=RunEventType.RUN_STARTED,
                payload={
                    "status": RunStatus.QUEUED.value,
                    "config": {
                        "quality_threshold": (
                            await self.manager.get_run(run_id)
                        ).quality_threshold,
                        "max_iterations": (
                            await self.manager.get_run(run_id)
                        ).max_iterations,
                        "mock": self.manager.provider.is_mock,
                    },
                },
            )
            await self.graph.ainvoke(
                {"run_id": run_id},  # type: ignore[arg-type]
                config={"recursion_limit": 40},
            )
        except WorkflowCancelled:
            await self.manager.finalize_cancel(run_id)
        except (ProviderAuthenticationError, InvalidModelError) as exc:
            await self._fail_unless_cancelled(
                run_id,
                code=exc.code,
                message="The configured provider rejected the request.",
                retryable=False,
            )
        except RetryableProviderError as exc:
            await self._fail_unless_cancelled(
                run_id,
                code=exc.code,
                message="The provider remained unavailable after retry.",
                retryable=True,
            )
        except TimeoutError:
            await self._fail_unless_cancelled(
                run_id,
                code="RUN_TIMEOUT",
                message="The run exceeded a configured timeout.",
                retryable=True,
            )
        except ValidationError:
            await self._fail_unless_cancelled(
                run_id,
                code="STRUCTURED_OUTPUT_INVALID",
                message="The provider returned invalid structured output.",
                retryable=False,
            )

    async def _fail_unless_cancelled(
        self,
        run_id: UUID,
        *,
        code: str,
        message: str,
        retryable: bool,
    ) -> None:
        if self.manager.is_cancel_requested(run_id):
            await self.manager.finalize_cancel(run_id)
            return
        await self.manager.fail_run(
            run_id,
            code=code,
            message=message,
            retryable=retryable,
        )

    async def _check_cancel(self, run_id: UUID) -> None:
        if self.manager.is_cancel_requested(run_id):
            raise WorkflowCancelled
        if self.manager.remaining_run_seconds(run_id) <= 0:
            raise TimeoutError

    async def _await_provider(
        self,
        run_id: UUID,
        awaitable: Awaitable[T],
        *,
        node_timeout: float,
    ) -> T:
        operation: asyncio.Future[T] = asyncio.ensure_future(awaitable)
        cancelled = asyncio.create_task(self.manager.cancel_signals[run_id].wait())
        try:
            await self._check_cancel(run_id)
            timeout = min(node_timeout, self.manager.remaining_run_seconds(run_id))
            done, _ = await asyncio.wait(  # type: ignore[type-var]
                {operation, cancelled},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                operation.cancel()
                raise TimeoutError
            if cancelled in done and cancelled.result():
                operation.cancel()
                raise WorkflowCancelled
            return operation.result()
        finally:
            cancelled.cancel()
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, cancelled, return_exceptions=True)

    async def _generator_node(self, graph_state: WorkflowState) -> dict[str, Any]:
        run_id = graph_state["run_id"]
        await self._check_cancel(run_id)
        state = await self.manager.set_stage(run_id, RunStatus.GENERATING)
        await self.manager.mark_node(
            run_id,
            "generator",
            NodeStatus.RUNNING,
            event=True,
        )
        plan = state.pending_revision_plan
        attempt = 0
        while attempt < 2:
            attempt += 1
            if attempt > 1:
                await self.manager.commit(
                    run_id,
                    lambda snapshot: setattr(snapshot, "current_prd", ""),
                    event=RunEventType.PRD_STREAM_RESET,
                    payload={
                        "version": state.current_iteration,
                        "attempt": attempt,
                    },
                )
            try:
                content, usage = await self._stream_generation(
                    run_id,
                    state,
                    plan,
                    attempt,
                )
                break
            except (RetryableProviderError, TimeoutError):
                if attempt >= 2:
                    raise
                log_event(
                    LOGGER,
                    "provider_retry",
                    run_id=run_id,
                    node="generator",
                    attempt=attempt + 1,
                    provider=type(self.manager.provider).__name__,
                )
        else:
            raise RetryableProviderError
        await self._check_cancel(run_id)
        version = PRDVersion(
            version=state.current_iteration,
            content=content,
            created_at=utc_now(),
            revision_plan=plan,
            token_usage=usage,
        )

        def finish_generation(snapshot: RunSnapshot) -> None:
            if self.manager.is_cancel_requested(run_id):
                raise WorkflowCancelled
            snapshot.versions.append(version)
            snapshot.current_prd = content
            snapshot.pending_revision_plan = None
            snapshot.node_statuses["generator"] = NodeStatus.SUCCEEDED
            snapshot.active_node = None

        await self.manager.commit(
            run_id,
            finish_generation,
            event=RunEventType.PRD_GENERATED,
            payload={
                "version": version.version,
                "attempt": attempt,
                "content": content,
            },
        )
        await self.manager.record_usage(run_id, node="generator", usage=usage)
        await self.manager.set_stage(run_id, RunStatus.REVIEWING)
        return {}

    async def _stream_generation(
        self,
        run_id: UUID,
        state: RunSnapshot,
        plan: RevisionPlan | None,
        attempt: int,
    ) -> tuple[str, TokenUsage]:
        iterator = self.manager.provider.stream_prd(
            user_idea=state.user_idea,
            target_audience=state.target_audience,
            user_constraints=state.user_constraints,
            iteration=state.current_iteration,
            revision_plan=plan,
        ).__aiter__()
        content = ""
        buffer = ""
        last_flush = monotonic()
        usage: TokenUsage | None = None
        deadline = monotonic() + min(
            self.manager.settings.generator_timeout_seconds,
            self.manager.remaining_run_seconds(run_id),
        )
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError
            try:
                event = await self._await_provider(
                    run_id,
                    iterator.__anext__(),
                    node_timeout=remaining,
                )
            except StopAsyncIteration:
                break
            if event.delta:
                content += event.delta
                buffer += event.delta
            now = monotonic()
            if buffer and (len(buffer) >= 128 or now - last_flush >= 0.05):
                await self._commit_delta(run_id, state, attempt, buffer)
                buffer = ""
                last_flush = now
            if event.usage is not None:
                usage = event.usage
        if buffer:
            await self._commit_delta(run_id, state, attempt, buffer)
        if usage is None:
            raise RetryableProviderError("Provider omitted token usage")
        return content, usage

    async def _commit_delta(
        self,
        run_id: UUID,
        state: RunSnapshot,
        attempt: int,
        delta: str,
    ) -> None:
        await self._check_cancel(run_id)

        def append_delta(snapshot: RunSnapshot) -> None:
            if self.manager.is_cancel_requested(run_id):
                raise WorkflowCancelled
            snapshot.current_prd += delta

        await self.manager.commit(
            run_id,
            append_delta,
            event=RunEventType.PRD_DELTA,
            payload={
                "version": state.current_iteration,
                "attempt": attempt,
                "delta": delta,
            },
        )

    async def _tech_reviewer_node(
        self,
        graph_state: WorkflowState,
    ) -> dict[str, Any]:
        await self._reviewer_node(graph_state["run_id"], ReviewRole.TECH)
        return {}

    async def _ux_reviewer_node(
        self,
        graph_state: WorkflowState,
    ) -> dict[str, Any]:
        await self._reviewer_node(graph_state["run_id"], ReviewRole.UX)
        return {}

    async def _biz_reviewer_node(
        self,
        graph_state: WorkflowState,
    ) -> dict[str, Any]:
        await self._reviewer_node(graph_state["run_id"], ReviewRole.BIZ)
        return {}

    async def _reviewer_node(self, run_id: UUID, role: ReviewRole) -> None:
        await self._check_cancel(run_id)
        node = f"{role.value}_reviewer"
        await self.manager.mark_node(
            run_id,
            node,
            NodeStatus.RUNNING,
            event=True,
            role=role.value,
        )
        state = await self.manager.get_run(run_id)

        async def call() -> ProviderStructuredResult:
            return await self.manager.provider.generate_review(
                role=role,
                prd=state.current_prd,
                iteration=state.current_iteration,
            )

        result, review = await self._validated_structured(
            run_id,
            call=call,
            model=RoleReview,
            kind="review",
            role=role,
            timeout_seconds=self.manager.settings.reviewer_timeout_seconds,
        )
        if review.role is not role:
            raise ValidationError.from_exception_data(
                "RoleReview",
                [],
            )
        await self._check_cancel(run_id)

        def finish_review(snapshot: RunSnapshot) -> None:
            if self.manager.is_cancel_requested(run_id):
                raise WorkflowCancelled
            snapshot.reviews[role] = review
            snapshot.node_statuses[node] = NodeStatus.SUCCEEDED
            if snapshot.active_node == node:
                snapshot.active_node = None

        await self.manager.commit(
            run_id,
            finish_review,
            event=RunEventType.REVIEW_COMPLETED,
            payload=review.model_dump(mode="json"),
        )
        await self.manager.record_usage(run_id, node=node, usage=result.usage)

    async def _validated_structured(
        self,
        run_id: UUID,
        *,
        call: Callable[[], Awaitable[ProviderStructuredResult]],
        model: type[T],
        kind: str,
        role: ReviewRole | None,
        timeout_seconds: float,
    ) -> tuple[ProviderStructuredResult, T]:
        result: ProviderStructuredResult | None = None
        for attempt in range(2):
            try:
                result = await self._await_provider(
                    run_id,
                    call(),
                    node_timeout=timeout_seconds,
                )
                break
            except (RetryableProviderError, TimeoutError):
                if attempt == 1:
                    raise
                log_event(
                    LOGGER,
                    "provider_retry",
                    run_id=run_id,
                    node=kind,
                    role=role,
                    attempt=attempt + 2,
                    provider=type(self.manager.provider).__name__,
                )
        assert result is not None
        try:
            parsed = model.model_validate(result.value)  # type: ignore[attr-defined]
            return result, parsed
        except ValidationError as exc:
            repaired = await self._await_provider(
                run_id,
                self.manager.provider.repair_structured(
                    kind=kind,
                    raw_value=result.value,
                    validation_error=str(exc),
                    role=role,
                ),
                node_timeout=timeout_seconds,
            )
            parsed = model.model_validate(repaired.value)  # type: ignore[attr-defined]
            combined_usage = TokenUsage(
                input_tokens=result.usage.input_tokens + repaired.usage.input_tokens,
                output_tokens=result.usage.output_tokens + repaired.usage.output_tokens,
                total_tokens=result.usage.total_tokens + repaired.usage.total_tokens,
            )
            repaired.usage = combined_usage
            return repaired, parsed

    async def _aggregator_node(self, graph_state: WorkflowState) -> dict[str, Any]:
        run_id = graph_state["run_id"]
        await self._check_cancel(run_id)
        await self.manager.set_stage(run_id, RunStatus.AGGREGATING)
        await self.manager.mark_node(
            run_id,
            "aggregator",
            NodeStatus.RUNNING,
            event=True,
        )
        state = await self.manager.get_run(run_id)
        if set(state.reviews) != set(ReviewRole):
            raise ValueError("All three independent reviews are required")
        tech = state.reviews[ReviewRole.TECH]
        ux = state.reviews[ReviewRole.UX]
        biz = state.reviews[ReviewRole.BIZ]
        evaluation = EvaluationResult(
            tech=tech,
            ux=ux,
            biz=biz,
            overall_score=round((tech.score + ux.score + biz.score) / 3, 1),
            combined_feedback=[
                *tech.feedback,
                *ux.feedback,
                *biz.feedback,
            ],
        )

        def aggregate(snapshot: RunSnapshot) -> None:
            snapshot.latest_evaluation = evaluation
            snapshot.node_statuses["aggregator"] = NodeStatus.SUCCEEDED
            snapshot.active_node = None
            if snapshot.versions:
                snapshot.versions[-1].evaluation = evaluation

        state = await self.manager.commit(
            run_id,
            aggregate,
            event=RunEventType.SCORES_UPDATED,
            payload={
                "tech": tech.score,
                "ux": ux.score,
                "biz": biz.score,
                "overall": evaluation.overall_score,
            },
        )
        if evaluation.overall_score >= state.quality_threshold:
            await self.manager.transition(
                run_id,
                RunStatus.COMPLETED,
                event=RunEventType.RUN_COMPLETED,
                payload={
                    "final_version": state.current_iteration,
                    "final_score": evaluation.overall_score,
                },
            )
            await self.manager.event_store.wake(run_id)
            return {}
        if state.current_iteration >= state.max_iterations:
            await self.manager.transition(
                run_id,
                RunStatus.MAX_ITERATIONS_REACHED,
                event=RunEventType.MAX_ITERATIONS_REACHED,
                payload={
                    "final_version": state.current_iteration,
                    "final_score": evaluation.overall_score,
                },
            )
            await self.manager.event_store.wake(run_id)
            return {}
        if state.status is RunStatus.PAUSE_REQUESTED:
            await self.manager.enter_paused(run_id)
            await self.manager.wait_until_resumed_or_cancelled(run_id)
            await self._check_cancel(run_id)
        else:
            await self.manager.set_stage(run_id, RunStatus.OPTIMIZING)
        return {}

    async def _route_after_aggregate(self, graph_state: WorkflowState) -> str:
        state = await self.manager.get_run(graph_state["run_id"])
        return "end" if state.status in TERMINAL_RUN_STATUSES else "optimizer"

    async def _optimizer_node(self, graph_state: WorkflowState) -> dict[str, Any]:
        run_id = graph_state["run_id"]
        await self._check_cancel(run_id)
        before_optimizer = await self.manager.get_run(run_id)
        if before_optimizer.status is RunStatus.PAUSE_REQUESTED:
            await self.manager.enter_paused(run_id)
            await self.manager.wait_until_resumed_or_cancelled(run_id)
            await self._check_cancel(run_id)
        stage = await self.manager.set_stage(run_id, RunStatus.OPTIMIZING)
        if stage.status is RunStatus.PAUSE_REQUESTED:
            await self.manager.enter_paused(run_id)
            await self.manager.wait_until_resumed_or_cancelled(run_id)
            await self._check_cancel(run_id)
            await self.manager.set_stage(run_id, RunStatus.OPTIMIZING)
        await self.manager.mark_node(
            run_id,
            "optimizer",
            NodeStatus.RUNNING,
            event=True,
        )
        state = await self.manager.get_run(run_id)
        if state.latest_evaluation is None:
            raise ValueError("Optimizer requires an evaluation")

        async def call() -> ProviderStructuredResult:
            assert state.latest_evaluation is not None
            return await self.manager.provider.generate_revision_plan(
                evaluation=state.latest_evaluation,
                iteration=state.current_iteration,
                user_override=state.pending_user_override,
            )

        result, plan = await self._validated_structured(
            run_id,
            call=call,
            model=RevisionPlan,
            kind="revision_plan",
            role=None,
            timeout_seconds=self.manager.settings.optimizer_timeout_seconds,
        )
        await self._check_cancel(run_id)

        def finish_optimizer(snapshot: RunSnapshot) -> None:
            if self.manager.is_cancel_requested(run_id):
                raise WorkflowCancelled
            snapshot.pending_revision_plan = plan
            snapshot.pending_user_override = None
            snapshot.node_statuses["optimizer"] = NodeStatus.SUCCEEDED
            snapshot.active_node = None
            snapshot.current_iteration += 1
            snapshot.reviews.clear()

        await self.manager.commit(
            run_id,
            finish_optimizer,
            event=RunEventType.REVISION_PLANNED,
            payload={"revision_plan": plan.model_dump(mode="json")},
        )
        await self.manager.record_usage(run_id, node="optimizer", usage=result.usage)
        await self.manager.set_stage(run_id, RunStatus.GENERATING)
        return {}
