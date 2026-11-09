from __future__ import annotations

from typing import Any

from backend.config import Settings
from backend.event_store import EventStore, SQLiteEventStore
from backend.provider_catalog import ProviderCatalog
from backend.providers.base import LLMProvider
from backend.providers.mock import MockLLMProvider
from backend.run_manager import RunManager
from backend.run_store import InMemoryRunStore, SQLiteRunStore
from backend.workflow import AgentWorkflow


def make_settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = {
        "_env_file": None,
        "database_path": ":memory:",
        "run_timeout_seconds": 10,
        "generator_timeout_seconds": 2,
        "reviewer_timeout_seconds": 2,
        "optimizer_timeout_seconds": 2,
        "event_buffer_size": 100,
        "sse_heartbeat_seconds": 5,
        "provider_retry_base_delay_seconds": 0,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_manager(
    *,
    provider: LLMProvider | None = None,
    settings: Settings | None = None,
    catalog: ProviderCatalog | None = None,
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
        catalog=catalog,
    )
    manager.set_workflow(AgentWorkflow(manager))
    return manager


def make_sqlite_manager(
    *,
    database_path: str,
    provider: LLMProvider | None = None,
    settings: Settings | None = None,
    catalog: ProviderCatalog | None = None,
) -> RunManager:
    """A manager backed by the real SQLite stores, as `create_app` wires them."""
    resolved_settings = settings or make_settings(database_path=database_path)
    resolved_provider = provider or MockLLMProvider(delays_enabled=False)
    store = SQLiteRunStore(
        database_path=database_path,
        max_runs=resolved_settings.max_retained_runs,
        ttl_seconds=resolved_settings.run_ttl_seconds,
    )
    events = SQLiteEventStore(
        database_path=database_path,
        buffer_size=resolved_settings.event_buffer_size,
        heartbeat_seconds=resolved_settings.sse_heartbeat_seconds,
        initial_sequences=store.initial_sequences(),
    )
    manager = RunManager(
        settings=resolved_settings,
        provider=resolved_provider,
        run_store=store,
        event_store=events,
        catalog=catalog,
    )
    manager.set_workflow(AgentWorkflow(manager))
    return manager


def finding(
    severity: Any,
    title: str,
    *,
    section: str = "5.1 Purchase Flow",
    category: Any = None,
    evidence: str | None = None,
    problem: str | None = None,
    confidence: float | None = 0.9,
) -> Any:
    """A model-shaped finding for test reviewers. Evidence defaults to present."""
    from backend.schemas import FindingCategory, FindingInput

    return FindingInput(
        title=title,
        severity=severity,
        category=category or FindingCategory.OTHER,
        section=section,
        evidence=f"Section {section} does not cover it."
        if evidence is None
        else evidence,
        problem=problem or f"{title}.",
        user_impact="The affected task cannot be completed reliably.",
        recommendation="Close the gap in the named section.",
        confidence=confidence,
    )


def review_value(
    role: Any,
    *,
    score: int,
    findings: list[Any] | None = None,
    resolutions: list[Any] | None = None,
) -> dict[str, Any]:
    """A ``ReviewerOutput`` value whose backend-computed role score is ``score``."""
    from backend.providers.mock import mock_review_output

    return mock_review_output(
        role,
        score=score,
        findings=findings or [],
        resolutions=resolutions,
    )


def role_review(
    role: Any,
    *,
    score: int,
    findings: list[Any] | None = None,
    version: int = 1,
) -> Any:
    """A stored ``RoleReview`` built the way the workflow builds one."""
    from backend.schemas import ReviewerOutput
    from backend.scoring import normalize_review

    return normalize_review(
        ReviewerOutput.model_validate(
            review_value(role, score=score, findings=findings)
        ),
        version=version,
    )
