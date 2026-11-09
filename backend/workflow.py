from __future__ import annotations

import asyncio
import inspect
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
    NodeTimeoutError,
    ProviderError,
    RetryableProviderError,
    RunTimeoutError,
)
from backend.failures import (
    NODE_STAGES,
    TRANSIENT_ATTEMPTS,
    backoff_seconds,
    classify,
    context_of,
    is_transient,
    tag,
)
from backend.observability import log_event, log_exception
from backend.prd_document import classify_finish_reason, validate_generated_prd
from backend.prd_quality import check_prd, outline, sections_matching
from backend.providers.base import (
    OptimizerContext,
    ProviderStructuredResult,
    ReviewContext,
    UserRequirements,
)
from backend.run_manager import RunManager
from backend.schemas import (
    EvaluationResult,
    FeedbackItem,
    NodeStatus,
    OptimizerOutput,
    PRDQualityReport,
    PRDVersion,
    ReviewerOutput,
    ReviewRole,
    RevisionPlan,
    RunEventType,
    RunSnapshot,
    RunStatus,
    TokenUsage,
    utc_now,
)
from backend.scoring import build_evaluation, build_revision_plan, normalize_review
from backend.state_machine import TERMINAL_RUN_STATUSES

T = TypeVar("T")
LOGGER = logging.getLogger("agentic_prd.workflow")


def _accepted(method: Callable[..., Any], **optional: Any) -> dict[str, Any]:
    """The subset of ``optional`` keyword arguments ``method`` declares.

    ``context`` and ``generation_mode`` were added to the provider interface in
    V2. A provider written against the earlier interface -- including every test
    double that overrides one method -- still works: it simply does not receive
    the new arguments, and degrades to the old behaviour for that call.
    """
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return {}
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return optional
    return {key: value for key, value in optional.items() if key in parameters}


#: Above this the optimizer gets an outline plus the sections its findings name,
#: instead of the whole document. Roughly 20k tokens of Chinese text.
OPTIMIZER_FULL_PRD_CHARACTERS = 60_000


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


def _requirements(state: RunSnapshot) -> UserRequirements:
    return UserRequirements(
        user_idea=state.user_idea,
        target_audience=state.target_audience,
        user_constraints=state.user_constraints,
    )


def _user_text(state: RunSnapshot) -> str:
    return "\n".join(
        part
        for part in (state.user_idea, state.target_audience, state.user_constraints)
        if part
    )


def _finding_payload(item: FeedbackItem) -> dict[str, Any]:
    """One finding as a model reads it: no merge bookkeeping, no observations."""
    return {
        key: value
        for key, value in {
            "finding_id": item.finding_id,
            "severity": item.severity.value,
            "category": item.category.value if item.category else None,
            "title": item.title,
            "section": item.section,
            "evidence": item.evidence,
            "problem": item.issue,
            "user_impact": item.user_impact,
            "recommendation": item.recommendation,
            "source_roles": [role.value for role in item.source_roles],
        }.items()
        if value not in (None, [], "")
    }


def _automated_checks(report: PRDQualityReport | None) -> list[str]:
    """The checker's findings as short lines a reviewer can confirm or discard."""
    if report is None:
        return []
    lines: list[str] = []
    for issue in report.issues:
        if issue.severity == "info":
            continue
        where = f" (line {issue.line})" if issue.line else ""
        excerpt = f' "{issue.excerpt}"' if issue.excerpt else ""
        lines.append(f"[{issue.code}] {issue.message}{where}{excerpt}")
    return lines[:20]


def _quality_summary(report: PRDQualityReport | None) -> dict[str, Any]:
    if report is None:
        return {}
    return {
        "characters": report.characters,
        "budget_characters": report.budget_characters,
        "long_paragraphs": report.long_paragraphs,
        "unlabeled_figures": report.unlabeled_figures,
        "structure_complete": report.structure_complete,
        "missing_sections": report.missing_sections,
        "issues": [
            {"code": issue.code, "message": issue.message, "section": issue.section}
            for issue in report.issues[:15]
        ],
    }


class AgentWorkflow:
    def __init__(self, manager: RunManager) -> None:
        self.manager = manager
        graph = StateGraph(WorkflowState)
        graph.add_node(  # type: ignore[call-overload]
            "generator", self._guard("generator", self._generator_node)
        )
        graph.add_node(  # type: ignore[call-overload]
            "tech_reviewer", self._guard("tech_reviewer", self._tech_reviewer_node)
        )
        graph.add_node(  # type: ignore[call-overload]
            "ux_reviewer", self._guard("ux_reviewer", self._ux_reviewer_node)
        )
        graph.add_node(  # type: ignore[call-overload]
            "biz_reviewer", self._guard("biz_reviewer", self._biz_reviewer_node)
        )
        graph.add_node(  # type: ignore[call-overload]
            "aggregator", self._guard("aggregator", self._aggregator_node)
        )
        graph.add_node(  # type: ignore[call-overload]
            "optimizer", self._guard("optimizer", self._optimizer_node)
        )
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

    def _guard(
        self,
        node: str,
        function: Callable[[WorkflowState], Awaitable[dict[str, Any]]],
    ) -> Callable[[WorkflowState], Awaitable[dict[str, Any]]]:
        """Label any exception with the node it came from.

        The three reviewers run in parallel, so "the last node marked RUNNING"
        names whichever reviewer started last, not the one that failed. Tagging
        at the node boundary names the one whose code actually raised.
        """

        async def guarded(graph_state: WorkflowState) -> dict[str, Any]:
            try:
                return await function(graph_state)
            except WorkflowCancelled:
                raise
            except Exception as exc:
                version: int | None = None
                try:
                    version = (
                        await self.manager.get_run(graph_state["run_id"])
                    ).current_iteration
                except Exception:  # pragma: no cover - the run is gone
                    version = None
                tag(exc, node=node, stage=NODE_STAGES[node], version=version)
                raise

        return guarded

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
                        "mock": self.manager.provider_for(run_id).is_mock,
                        "generation_mode": (
                            await self.manager.get_run(run_id)
                        ).generation_mode.value,
                    },
                },
            )
            await self.graph.ainvoke(
                {"run_id": run_id},  # type: ignore[arg-type]
                config={"recursion_limit": 40},
            )
        except WorkflowCancelled:
            await self.manager.finalize_cancel(run_id)
        except Exception as exc:
            await self._handle_failure(run_id, exc)

    async def _handle_failure(self, run_id: UUID, exc: Exception) -> None:
        if self.manager.is_cancel_requested(run_id):
            await self.manager.finalize_cancel(run_id)
            return
        state = await self.manager.get_run(run_id)
        info = classify(exc, has_best_version=state.best_version is not None)
        context = context_of(exc)
        fields = {
            "run_id": run_id,
            "trace_id": state.trace_id,
            "node": context.get("node"),
            "stage": context.get("stage"),
            "version": context.get("version"),
            "attempt": context.get("attempt"),
            "error_code": info.code,
            "provider": state.provider_id
            or type(self.manager.provider_for(run_id)).__name__,
            "model": state.model_id,
        }
        if info.code in {
            "WORKFLOW_FAILED",
            "STRUCTURED_OUTPUT_INVALID",
        } or not isinstance(exc, ProviderError | TimeoutError | ValidationError):
            # Unknown causes are the ones nobody can diagnose from a code alone,
            # so they keep their (redacted) stack.
            log_exception(LOGGER, "workflow_failed", exc, **fields)
        else:
            log_event(LOGGER, "workflow_failed", level=logging.WARNING, **fields)
        await self.manager.fail_run(
            run_id,
            code=info.code,
            message=info.message,
            retryable=info.retryable,
            node=_text(context.get("node")),
            stage=_text(context.get("stage")),
            version=_number(context.get("version")),
            attempt=_number(context.get("attempt")),
            recovery_action=info.recovery_action,
            category=info.category,
        )

    async def _check_cancel(self, run_id: UUID) -> None:
        if self.manager.is_cancel_requested(run_id):
            raise WorkflowCancelled
        if self.manager.remaining_run_seconds(run_id) <= 0:
            raise RunTimeoutError

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
            remaining = self.manager.remaining_run_seconds(run_id)
            run_bound = remaining < node_timeout
            timeout = min(node_timeout, remaining)
            done, _ = await asyncio.wait(  # type: ignore[type-var]
                {operation, cancelled},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                operation.cancel()
                raise RunTimeoutError if run_bound else NodeTimeoutError
            if cancelled in done and cancelled.result():
                operation.cancel()
                raise WorkflowCancelled
            return operation.result()
        finally:
            cancelled.cancel()
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, cancelled, return_exceptions=True)

    async def _backoff(self, run_id: UUID, error: BaseException, attempt: int) -> None:
        """Wait before retrying a transient failure; a cancel ends the wait."""
        delay = min(
            backoff_seconds(
                error, attempt, self.manager.settings.provider_retry_base_delay_seconds
            ),
            max(0.0, self.manager.remaining_run_seconds(run_id) - 1),
        )
        if delay <= 0:
            return
        try:
            await asyncio.wait_for(
                self.manager.cancel_signals[run_id].wait(), timeout=delay
            )
        except TimeoutError:
            return
        raise WorkflowCancelled

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
        if plan is None and not state.versions and state.seed_revision_plan:
            plan = state.seed_revision_plan
        attempt = 0
        # Reused across attempts so a failed one can still report what it spent.
        record = _AttemptRecord()
        while True:
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
            except WorkflowCancelled:
                raise
            except Exception as exc:
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
                    await self.manager.record_usage(
                        run_id,
                        node="generator",
                        usage=record.usage,
                    )
                tag(exc, attempt=attempt, version=state.current_iteration)
                # Only a failure the *same* request can get past is retried. An
                # output-cap truncation is not one: the identical request needs
                # the identical length, so it fails here, once, and the user is
                # offered a compact regeneration instead.
                if not is_transient(exc) or attempt >= TRANSIENT_ATTEMPTS:
                    raise
                log_event(
                    LOGGER,
                    "provider_retry",
                    run_id=run_id,
                    trace_id=state.trace_id,
                    node="generator",
                    attempt=attempt + 1,
                    reason=type(exc).__name__,
                    provider=type(self.manager.provider_for(run_id)).__name__,
                )
                await self._backoff(run_id, exc, attempt)
        await self._check_cancel(run_id)
        elapsed = record.seconds
        quality = check_prd(
            content, user_text=_user_text(state), mode=state.generation_mode
        )
        version = PRDVersion(
            version=state.current_iteration,
            content=content,
            created_at=utc_now(),
            revision_plan=plan,
            token_usage=usage,
            quality=quality,
            generation_mode=state.generation_mode,
        )

        def finish_generation(snapshot: RunSnapshot) -> None:
            if self.manager.is_cancel_requested(run_id):
                raise WorkflowCancelled
            snapshot.versions.append(version)
            snapshot.current_prd = content
            snapshot.current_prd_attempt = attempt
            snapshot.pending_revision_plan = None
            snapshot.incomplete_draft = None
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
                "quality": quality.model_dump(mode="json"),
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
        provider = self.manager.provider_for(run_id)
        iterator = provider.stream_prd(
            user_idea=state.user_idea,
            target_audience=state.target_audience,
            user_constraints=state.user_constraints,
            iteration=state.current_iteration,
            revision_plan=plan,
            baseline_prd=self._baseline_prd(state),
            output_language=state.output_language,
            **_accepted(provider.stream_prd, generation_mode=state.generation_mode),
        ).__aiter__()
        content = ""
        buffer = ""
        last_flush = monotonic()
        usage: TokenUsage | None = None
        finish_reason: str | None = None
        node_budget = self.manager.settings.generator_timeout_seconds
        run_budget = self.manager.remaining_run_seconds(run_id)
        run_bound = run_budget < node_budget
        deadline = monotonic() + min(node_budget, run_budget)
        while True:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise RunTimeoutError if run_bound else NodeTimeoutError
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
            trace_id=state.trace_id,
            node="generator",
            attempt=attempt,
            version=state.current_iteration,
            finish_reason=finish_reason,
            finish_verdict=classify_finish_reason(finish_reason),
            characters=len(content),
            output_tokens=usage.output_tokens if usage else None,
            generation_mode=state.generation_mode,
        )
        # Validated before the usage check, so the reader is told why the document
        # is unusable rather than that the provider forgot to meter it.
        validated = validate_generated_prd(content, finish_reason)
        if usage is None:
            raise RetryableProviderError("Provider omitted token usage")
        return validated, usage

    @staticmethod
    def _baseline_prd(state: RunSnapshot) -> str | None:
        """The document the next generation should edit rather than replace.

        The best version so far, not the latest: when a round regresses, the next
        attempt should start from the strongest text the run has produced. On the
        first iteration of a fresh run there is nothing to edit; a recovery run
        that continues from another run's best version edits that seed instead.
        """
        if not state.versions:
            return state.seed_prd
        if state.best_version is not None:
            for version in state.versions:
                if version.version == state.best_version:
                    return version.content
        return state.versions[-1].content

    @staticmethod
    def _baseline_version(state: RunSnapshot) -> PRDVersion | None:
        if not state.versions:
            return None
        if state.best_version is not None:
            for version in state.versions:
                if version.version == state.best_version:
                    return version
        return state.versions[-1]

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

    @staticmethod
    def _previous_evaluation(
        state: RunSnapshot,
    ) -> tuple[EvaluationResult | None, RevisionPlan | None]:
        """The evaluation the current version's plan was built from, and that plan."""
        if not state.versions:
            return None, None
        current = state.versions[-1]
        plan = current.revision_plan
        if plan is None:
            return None, None
        for version in state.versions:
            if version.version == plan.iteration and version.evaluation is not None:
                return version.evaluation, plan
        return None, plan

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
        previous, plan = self._previous_evaluation(state)
        previous_findings = [
            _finding_payload(item)
            for item in (previous.combined_feedback if previous else [])
            if item.finding_id is not None
            and (role in item.source_roles or item.source_role is role)
        ]
        context = ReviewContext(
            requirements=_requirements(state),
            automated_checks=_automated_checks(
                state.versions[-1].quality if state.versions else None
            ),
            previous_findings=previous_findings,
        )

        async def call() -> ProviderStructuredResult:
            provider = self.manager.provider_for(run_id)
            return await provider.generate_review(
                role=role,
                prd=state.current_prd,
                iteration=state.current_iteration,
                output_language=state.output_language,
                **_accepted(provider.generate_review, context=context),
            )

        result, output, attempts = await self._validated_structured(
            run_id,
            call=call,
            model=ReviewerOutput,
            kind="review",
            role=role,
            timeout_seconds=self.manager.settings.reviewer_timeout_seconds,
            output_language=state.output_language,
        )
        if output.role is not role:
            raise ValidationError.from_exception_data("ReviewerOutput", [])
        review = normalize_review(
            output,
            version=state.current_iteration,
            previous_finding_ids=[
                str(item["finding_id"]) for item in previous_findings
            ],
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
            attempt=attempts,
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
    ) -> tuple[ProviderStructuredResult, T, int]:
        """Call, retry transient failures with backoff, repair invalid output once.

        Returns the result, the parsed value, and how many calls were made. A
        second invalid answer is final: one repair is the whole budget.
        """
        result: ProviderStructuredResult | None = None
        attempt = 0
        while True:
            attempt += 1
            try:
                result = await self._await_provider(
                    run_id,
                    call(),
                    node_timeout=timeout_seconds,
                )
                break
            except WorkflowCancelled:
                raise
            except Exception as exc:
                tag(exc, attempt=attempt)
                if not is_transient(exc) or attempt >= TRANSIENT_ATTEMPTS:
                    raise
                log_event(
                    LOGGER,
                    "provider_retry",
                    run_id=run_id,
                    node=kind,
                    role=role,
                    attempt=attempt + 1,
                    reason=type(exc).__name__,
                    provider=type(self.manager.provider_for(run_id)).__name__,
                )
                await self._backoff(run_id, exc, attempt)
        assert result is not None
        try:
            parsed = model.model_validate(result.value)  # type: ignore[attr-defined]
            return result, parsed, attempt
        except ValidationError as exc:
            log_event(
                LOGGER,
                "structured_output_repair",
                level=logging.WARNING,
                run_id=run_id,
                node=kind,
                role=role,
                errors=exc.error_count(),
            )
            repaired = await self._await_provider(
                run_id,
                self.manager.provider_for(run_id).repair_structured(
                    kind=kind,
                    raw_value=result.value,
                    validation_error=str(exc),
                    role=role,
                    output_language=output_language,
                ),
                node_timeout=timeout_seconds,
            )
            try:
                parsed = model.model_validate(repaired.value)  # type: ignore[attr-defined]
            except ValidationError as repair_error:
                tag(repair_error, attempt=attempt + 1)
                raise
            combined_usage = TokenUsage(
                input_tokens=result.usage.input_tokens + repaired.usage.input_tokens,
                output_tokens=result.usage.output_tokens + repaired.usage.output_tokens,
                total_tokens=result.usage.total_tokens + repaired.usage.total_tokens,
            )
            repaired.usage = combined_usage
            return repaired, parsed, attempt + 1

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
        previous, previous_plan = self._previous_evaluation(state)
        # Scores, dedup, the gate and the resolution of earlier findings are all
        # computed here, deterministically, from what the reviewers returned.
        evaluation, gate = build_evaluation(
            tech,
            ux,
            biz,
            quality_threshold=state.quality_threshold,
            previous=previous,
            previous_plan=previous_plan,
        )

        previous_best = state.best_score
        improved = previous_best is None or evaluation.overall_score > previous_best
        best_score = evaluation.overall_score if improved else previous_best
        best_version = state.current_iteration if improved else state.best_version

        severity_counts = evaluation.severity_counts()
        must_fix_count = gate.must_fix_count
        threshold_met = gate.threshold_met
        gate_passed = gate.passed

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
                "must_fix_count": must_fix_count,
                "should_fix_count": severity_counts["should_fix"],
                "optional_count": severity_counts["optional"],
                "quality_gate_passed": gate_passed,
                "gate_status": gate.status.value,
                "findings_before_dedup": evaluation.findings_before_dedup,
                "findings_after_dedup": len(evaluation.combined_feedback),
                "rubric_version": evaluation.rubric_version,
                "scoring_version": evaluation.scoring_version,
                "combined_feedback": [
                    item.model_dump(mode="json")
                    for item in evaluation.combined_feedback
                ],
                "finding_resolutions": [
                    item.model_dump(mode="json")
                    for item in evaluation.finding_resolutions
                ],
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
            "gate_status": gate.status.value,
            "must_fix_count": must_fix_count,
            "should_fix_count": severity_counts["should_fix"],
            "optional_count": severity_counts["optional"],
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

    def _optimizer_context(
        self, state: RunSnapshot, evaluation: EvaluationResult
    ) -> OptimizerContext:
        baseline = self._baseline_version(state)
        prd = baseline.content if baseline else state.current_prd
        excerpt = False
        if len(prd) > OPTIMIZER_FULL_PRD_CHARACTERS:
            # Too long to send whole: the outline shows every chapter, and the
            # sections the findings name come through in full, so the optimizer
            # still sees every place a changed rule might also be stated.
            sections = [
                item.section for item in evaluation.combined_feedback if item.section
            ]
            prd = (
                "OUTLINE\n"
                + "\n".join(outline(prd))
                + "\n\nRELEVANT SECTIONS\n"
                + sections_matching(prd, sections)
            )[:OPTIMIZER_FULL_PRD_CHARACTERS]
            excerpt = True
        return OptimizerContext(
            requirements=_requirements(state),
            prd=prd,
            prd_is_excerpt=excerpt,
            reviewed_version=state.current_iteration,
            baseline_version=baseline.version if baseline else state.current_iteration,
            findings=[_finding_payload(item) for item in evaluation.combined_feedback],
            role_scores={
                "tech": evaluation.tech.score,
                "ux": evaluation.ux.score,
                "biz": evaluation.biz.score,
            },
            quality_report=_quality_summary(baseline.quality if baseline else None),
        )

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
        evaluation = state.latest_evaluation
        if evaluation is None:
            raise ValueError("Optimizer requires an evaluation")
        context = self._optimizer_context(state, evaluation)

        async def call() -> ProviderStructuredResult:
            provider = self.manager.provider_for(run_id)
            return await provider.generate_revision_plan(
                evaluation=evaluation,
                iteration=state.current_iteration,
                user_override=state.pending_user_override,
                output_language=state.output_language,
                **_accepted(provider.generate_revision_plan, context=context),
            )

        result, output, attempts = await self._validated_structured(
            run_id,
            call=call,
            model=OptimizerOutput,
            kind="revision_plan",
            role=None,
            timeout_seconds=self.manager.settings.optimizer_timeout_seconds,
            output_language=state.output_language,
        )
        plan = build_revision_plan(
            output,
            iteration=state.current_iteration,
            findings=evaluation.combined_feedback,
            user_override=state.pending_user_override,
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
            attempt=attempts,
            seconds=monotonic() - started,
            succeeded=True,
            usage=result.usage,
        )
        await self.manager.set_stage(run_id, RunStatus.GENERATING)
        return {}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _number(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
