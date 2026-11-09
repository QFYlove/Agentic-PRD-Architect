"""Condition B: the product's full workflow, run headlessly with product defaults."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backend.config import Settings
from backend.event_store import EventStore
from backend.provider_catalog import (
    CatalogModel,
    CatalogProvider,
    ModelPricing,
    ProviderCatalog,
)
from backend.providers.base import LLMProvider
from backend.run_manager import RunManager
from backend.run_store import InMemoryRunStore
from backend.schemas import CreateRunRequest, RunSnapshot
from backend.workflow import AgentWorkflow
from prd_benchmark.config import ConditionB, ModelConfig

#: Prefix no real variable uses: Settings then ignores the process environment.
ISOLATED_ENV_PREFIX = "PRD_BENCHMARK_ISOLATED_"


def make_settings(condition: ConditionB) -> Settings:
    """Product settings for a benchmark run, isolated from the environment.

    ``_env_file=None`` keeps ``.env`` unread, and the unused env prefix keeps
    process variables (``DEEPSEEK_API_KEY``, ``RUN_TIMEOUT_SECONDS`` ...) from
    leaking in, so every value below is either explicit or a product default.
    ``database_path`` is in-memory so ``data/agentic-prd.sqlite3`` is never
    opened.

    ``enable_mock_llm`` only selects a provider inside ``create_app``, which the
    harness does not call; the provider is injected. Its default (true) skips
    the key check, so the API key never enters ``Settings`` at all and exists
    only inside the SDK client.
    """
    timeouts = condition.timeouts_seconds
    return Settings(
        _env_file=None,
        _env_prefix=ISOLATED_ENV_PREFIX,
        database_path=":memory:",
        generator_timeout_seconds=timeouts.generator,
        reviewer_timeout_seconds=timeouts.reviewer,
        optimizer_timeout_seconds=timeouts.optimizer,
        run_timeout_seconds=timeouts.run,
        mock_delays_enabled=False,
    )


def make_manager(
    provider: LLMProvider, model: ModelConfig, settings: Settings
) -> RunManager:
    """Wire the product's manager exactly as ``create_app`` does, minus HTTP."""
    catalog = ProviderCatalog(
        (
            CatalogProvider(
                model.provider_id,
                model.provider_id,
                (
                    CatalogModel(
                        model.model_id,
                        model.model_id,
                        model.provider_id,
                        provider,
                        ModelPricing(),
                    ),
                ),
            ),
        )
    )
    manager = RunManager(
        settings=settings,
        provider=provider,
        run_store=InMemoryRunStore(
            max_runs=settings.max_retained_runs,
            ttl_seconds=settings.run_ttl_seconds,
        ),
        event_store=EventStore(
            buffer_size=settings.event_buffer_size,
            heartbeat_seconds=settings.sse_heartbeat_seconds,
        ),
        catalog=catalog,
    )
    manager.set_workflow(AgentWorkflow(manager))
    return manager


@dataclass
class WorkflowResult:
    status: str
    error_code: str | None
    harness_wait_timed_out: bool
    started_at: str
    ended_at: str
    wall_seconds: float
    snapshot: RunSnapshot

    @property
    def versions(self) -> dict[int, str]:
        return {v.version: v.content for v in self.snapshot.versions}

    def documents(self) -> dict[str, str]:
        """``B.best`` / ``B.last`` / ``B.v1`` for whatever versions exist."""
        versions = self.versions
        documents: dict[str, str] = {}
        best = self.snapshot.best_version
        if best is not None and best in versions:
            documents["B.best"] = versions[best]
        if versions:
            documents["B.last"] = versions[max(versions)]
        if 1 in versions:
            documents["B.v1"] = versions[1]
        return documents

    def meta(self) -> dict[str, Any]:
        snapshot = self.snapshot
        evaluations = {
            v.version: v.evaluation.overall_score if v.evaluation else None
            for v in snapshot.versions
        }
        return {
            "status": self.status,
            "error_code": self.error_code,
            "harness_wait_timed_out": self.harness_wait_timed_out,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "wall_seconds": self.wall_seconds,
            "elapsed_seconds": snapshot.elapsed_seconds,
            "best_version": snapshot.best_version,
            "best_score": snapshot.best_score,
            "last_version": max(self.versions) if self.versions else None,
            "version_count": len(snapshot.versions),
            "internal_scores": evaluations,
            "quality_gate_passed": self.status == "COMPLETED",
            "snapshot_total_tokens": snapshot.total_tokens.model_dump(),
        }


async def run_condition_b(
    request: CreateRunRequest,
    provider: LLMProvider,
    *,
    model: ModelConfig,
    condition: ConditionB,
) -> WorkflowResult:
    """Run one full workflow to a terminal state and return its snapshot."""
    settings = make_settings(condition)
    manager = make_manager(provider, model, settings)
    run_request = CreateRunRequest(
        user_idea=request.user_idea,
        target_audience=request.target_audience,
        user_constraints=request.user_constraints,
        quality_threshold=condition.quality_threshold,
        max_iterations=condition.max_iterations,
        provider_id=model.provider_id,
        model_id=model.model_id,
    )
    started_at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    timed_out = False
    try:
        created = await manager.create_run(run_request)
        try:
            await manager.wait_for_completion(
                created.run_id,
                wait_seconds=condition.wait_for_completion_seconds,
            )
        except TimeoutError:
            # The product's own run timeout should always fire first; reaching
            # here means the harness wait was misconfigured. Cancel, record it.
            timed_out = True
            await manager.cancel_run(created.run_id)
        snapshot = await manager.get_run(created.run_id)
    finally:
        await manager.shutdown()
    return WorkflowResult(
        status=snapshot.status.value,
        error_code=snapshot.error.code if snapshot.error else None,
        harness_wait_timed_out=timed_out,
        started_at=started_at,
        ended_at=datetime.now(UTC).isoformat(),
        wall_seconds=round(time.monotonic() - started, 3),
        snapshot=snapshot,
    )
