from __future__ import annotations

from typing import Any

from backend.config import Settings
from backend.event_store import EventStore
from backend.providers.base import LLMProvider
from backend.providers.mock import MockLLMProvider
from backend.run_manager import RunManager
from backend.run_store import InMemoryRunStore
from backend.workflow import AgentWorkflow


def make_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "_env_file": None,
        "run_timeout_seconds": 10,
        "generator_timeout_seconds": 2,
        "reviewer_timeout_seconds": 2,
        "optimizer_timeout_seconds": 2,
        "event_buffer_size": 100,
        "sse_heartbeat_seconds": 5,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_manager(
    *,
    provider: LLMProvider | None = None,
    settings: Settings | None = None,
) -> RunManager:
    resolved_settings = settings or make_settings()
    resolved_provider = provider or MockLLMProvider(delays_enabled=False)
    store = InMemoryRunStore(
        max_runs=resolved_settings.max_retained_runs,
        ttl_seconds=resolved_settings.run_ttl_seconds,
    )
    events = EventStore(
        buffer_size=resolved_settings.event_buffer_size,
        heartbeat_seconds=resolved_settings.sse_heartbeat_seconds,
    )
    manager = RunManager(
        settings=resolved_settings,
        provider=resolved_provider,
        run_store=store,
        event_store=events,
    )
    manager.set_workflow(AgentWorkflow(manager))
    return manager
