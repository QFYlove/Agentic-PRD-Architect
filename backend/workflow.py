from __future__ import annotations

import asyncio
import logging
import warnings
from collections.abc import Awaitable, Callable
from functools import partial
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
    ProviderError,
    RetryableProviderError,
)
from backend.observability import log_event
from backend.prd_document import classify_finish_reason, validate_generated_prd
from backend.providers.base import ProviderStructuredResult
from backend.run_manager import RunManager
from backend.schemas import (
    EvaluationResult,
    FeedbackSeverity,
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


class _AttemptRecord:
    """What one generation attempt has spent so far.

    A failed attempt raises out of the stream, so its duration and whatever usage
    the provider had already reported are only recoverable if something outside
    the ``try`` is holding them. That is all this is.
    """

    def __init__(self) -> None:
        self.started = monotonic()
        self.usage: TokenUsage | None = None

    def restart(self) -> None:
        self.started = monotonic()
        self.usage = None

    @property
    def seconds(self) -> float:
        return monotonic() - self.started


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
                message=exc.user_message,
                retryable=False,
            )
        except RetryableProviderError as exc:
            await self._fail_unless_cancelled(
                run_id,
                code=exc.code,
                message=exc.user_message,
                retryable=True,
            )
        except ProviderError as exc:
            # Any translated provider failure keeps its own stable code instead
            # of degrading into the generic WORKFLOW_FAILED from RunManager.
            await self._fail_unless_cancelled(
                run_id,
                code=exc.code,
                message=exc.user_message,
                retryable=exc.retryable,
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
        # Reused across attempts so a failed one can still report what it spent.
        record = _AttemptRecord()
        while attempt < 2:
            attempt += 1
            record.restart()
            begin_stream = partial(self._begin_stream, attempt=attempt)
            if attempt > 1:
                await self.manager.commit(
                    run_id,
                    begin_stream,
                    event=RunEventType.PRD_STREAM_RESET,
                    payload={
                        "version": state.current_iteration,
                        "attempt": attempt,
                    },
                )
            else:
                # No event: live clients already scope deltas by version, and
                # the previous iteration's text stays reachable through
                # `versions`. The commit exists so a client that loads the
                # snapshot mid-generation rebuilds its draft from this
                # iteration's partial text only, tagged with this attempt.
                await self.manager.commit(run_id, begin_stream)
            try:
                content, usage = await self._stream_generation(
                    run_id,
                    state,
                    plan,
                    attempt,
                    record,
                )
                break
            except (RetryableProviderError, TimeoutError):
                # A failed attempt still spent wall-clock time and, when the
                # provider reported usage before breaking off, tokens. Both are
                # recorded here: a run that spent 500 seconds and threw two of
                # them away has to show that, or the timings do not add up.
                await self.manager.record_timing(
                    run_id,
                    node="generator",
                    version=state.current_iteration,
                    attempt=attempt,
                    seconds=record.seconds,
                    succeeded=False,
                    usage=record.usage,
                )
                if record.usage is not None:
                    # Previously dropped: a truncated attempt's tokens were billed
                    # by the provider but never reached `total_tokens`, so a run
                    # that failed on its second attempt under-reported its spend.
                    await self.manager.record_usage(
                        run_id,
                        node="generator",
                        usage=record.usage,
                    )
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
        elapsed = record.seconds
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
            snapshot.current_prd_attempt = attempt
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
        await self.manager.record_timing(
            run_id,
            node="generator",
            version=version.version,
            attempt=attempt,
            seconds=elapsed,
            succeeded=True,
            usage=usage,
        )
        await self.manager.set_stage(run_id, RunStatus.REVIEWING)
        return {}

    @staticmethod
    def _begin_stream(snapshot: RunSnapshot, *, attempt: int) -> None:
        """Clear the streaming buffer and record which attempt now owns it."""
        snapshot.current_prd = ""
        snapshot.current_prd_attempt = attempt

    async def _stream_generation(
        self,
        run_id: UUID,
        state: RunSnapshot,
        plan: RevisionPlan | None,
        attempt: int,
        record: _AttemptRecord,
    ) -> tuple[str, TokenUsage]:
        iterator = self.manager.provider.stream_prd(
            user_idea=state.user_idea,
            target_audience=state.target_audience,
            user_constraints=state.user_constraints,
            iteration=state.current_iteration,
            revision_plan=plan,
            baseline_prd=self._baseline_prd(state),
            output_language=state.output_language,
        ).__aiter__()
        content = ""
        buffer = ""
        last_flush = monotonic()
        usage: TokenUsage | None = None
        finish_reason: str | None = None
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
                # Mirrored onto the record so the retry path can report the spend
                # of an attempt that raises after the provider billed it.
                record.usage = event.usage
            if event.finish_reason:
                finish_reason = event.finish_reason
        if buffer:
            await self._commit_delta(run_id, state, attempt, buffer)
        # The raw reason is a provider-supplied string, so it goes to the
        # structured log and never into an error the client can read; the
        # exceptions below carry only their own fixed `user_message`.
        log_event(
            LOGGER,
            "generation_finished",
            run_id=run_id,
            node="generator",
            attempt=attempt,
            version=state.current_iteration,
            finish_reason=finish_reason,
            finish_verdict=classify_finish_reason(finish_reason),
            characters=len(content),
        )
        # Validated before the usage check, so the reader is told why the document
        # is unusable rather than that the provider forgot to meter it: a
        # truncated stream that also omits usage is a length problem, and
        # 「模型服务暂时不可用」 would send them to retry an identical request.
        validated = validate_generated_prd(content, finish_reason)
        if usage is None:
            raise RetryableProviderError("Provider omitted token usage")
        return validated, usage

    @staticmethod
    def _baseline_prd(state: RunSnapshot) -> str | None:
        """The document the next generation should edit rather than replace.

        The best version so far, not the latest: when a round regresses, the next
        attempt should start from the strongest text the run has produced. On the
        first iteration there is nothing to edit and the generator writes fresh.
        """
        if not state.versions:
            return None
        if state.best_version is not None:
            for version in state.versions:
                if version.version == state.best_version:
                    return version.content
        return state.versions[-1].content

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
        started = monotonic()
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
                output_language=state.output_language,
            )

        result, review = await self._validated_structured(
            run_id,
            call=call,
            model=RoleReview,
            kind="review",
            role=role,
            timeout_seconds=self.manager.settings.reviewer_timeout_seconds,
            output_language=state.output_language,
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
        await self.manager.record_timing(
            run_id,
            node=node,
            version=state.current_iteration,
            attempt=1,
            seconds=monotonic() - started,
            succeeded=True,
            usage=result.usage,
        )

    async def _validated_structured(
        self,
        run_id: UUID,
        *,
        call: Callable[[], Awaitable[ProviderStructuredResult]],
        model: type[T],
        kind: str,
        role: ReviewRole | None,
        timeout_seconds: float,
        output_language: str,
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
                    output_language=output_language,
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

        previous_best = state.best_score
        improved = previous_best is None or evaluation.overall_score > previous_best
        best_score = evaluation.overall_score if improved else previous_best
        best_version = state.current_iteration if improved else state.best_version

        # The quality gate is a conjunction: a score target is an early-stop
        # goal, and blocking findings are a correctness floor. Reaching the
        # score while a reviewer still says a core flow cannot be built is not
        # a finished document, so both halves must hold before a run completes.
        severity_counts = evaluation.severity_counts()
        must_fix_count = severity_counts[FeedbackSeverity.MUST_FIX.value]
        threshold_met = evaluation.overall_score >= state.quality_threshold
        gate_passed = threshold_met and must_fix_count == 0

        def aggregate(snapshot: RunSnapshot) -> None:
            snapshot.latest_evaluation = evaluation
            snapshot.node_statuses["aggregator"] = NodeStatus.SUCCEEDED
            snapshot.active_node = None
            if snapshot.versions:
                snapshot.versions[-1].evaluation = evaluation
            snapshot.best_score = best_score
            snapshot.best_version = best_version

        state = await self.manager.commit(
            run_id,
            aggregate,
            event=RunEventType.SCORES_UPDATED,
            payload={
                "tech": tech.score,
                "ux": ux.score,
                "biz": biz.score,
                "overall": evaluation.overall_score,
                "version": state.current_iteration,
                # A signed delta against the previous best, computed here rather
                # than asked of a reviewer: the reviewers score one document at a
                # time and must never see a target to beat.
                "delta_vs_best": (
                    None
                    if previous_best is None
                    else round(evaluation.overall_score - previous_best, 1)
                ),
                "best_version": best_version,
                "best_score": best_score,
                # Open findings by tier for the version just scored. The client
                # shows these next to the score so "target reached" and "one
                # blocker still open" can be read at the same time.
                "must_fix_count": must_fix_count,
                "should_fix_count": severity_counts[FeedbackSeverity.SHOULD_FIX.value],
                "optional_count": severity_counts[FeedbackSeverity.OPTIONAL.value],
                "quality_gate_passed": gate_passed,
            },
        )
        outcome = {
            "final_version": state.current_iteration,
            "final_score": evaluation.overall_score,
            "best_version": state.best_version,
            "best_score": state.best_score,
            "quality_threshold": state.quality_threshold,
            "completed_iterations": state.current_iteration,
            "max_iterations": state.max_iterations,
            "threshold_met": threshold_met,
            # The gate has two independent halves, so both are reported: a run
            # that scored well can still be held by one blocking finding, and a
            # run that ran out of budget with blockers open must not be
            # presented as having met its quality goal.
            "quality_gate_passed": gate_passed,
            "must_fix_count": severity_counts[FeedbackSeverity.MUST_FIX.value],
            "should_fix_count": severity_counts[FeedbackSeverity.SHOULD_FIX.value],
            "optional_count": severity_counts[FeedbackSeverity.OPTIONAL.value],
        }
        if gate_passed:
            await self.manager.transition(
                run_id,
                RunStatus.COMPLETED,
                event=RunEventType.RUN_COMPLETED,
                payload=outcome,
            )
            await self.manager.event_store.wake(run_id)
            return {}
        if state.current_iteration >= state.max_iterations:
            # `max_iterations` is an attempt budget, so exhausting it is a normal
            # ending, not a failure -- but the payload has to say plainly whether
            # the threshold went unmet, whether blocking findings are still open,
            # and which version actually scored best.
            await self.manager.transition(
                run_id,
                RunStatus.MAX_ITERATIONS_REACHED,
                event=RunEventType.MAX_ITERATIONS_REACHED,
                payload=outcome,
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
        # Started after the pause handling above, so a run parked by the user does
        # not read back as a slow optimizer.
        started = monotonic()
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
                output_language=state.output_language,
            )

        result, plan = await self._validated_structured(
            run_id,
            call=call,
            model=RevisionPlan,
            kind="revision_plan",
            role=None,
            timeout_seconds=self.manager.settings.optimizer_timeout_seconds,
            output_language=state.output_language,
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
        await self.manager.record_timing(
            run_id,
            node="optimizer",
            version=state.current_iteration,
            attempt=1,
            seconds=monotonic() - started,
            succeeded=True,
            usage=result.usage,
        )
        await self.manager.set_stage(run_id, RunStatus.GENERATING)
        return {}
