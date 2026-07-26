from __future__ import annotations

import asyncio
from datetime import timedelta
from time import monotonic
from uuid import UUID

from backend.main import create_app
from backend.providers.mock import MockLLMProvider
from backend.schemas import CreateRunRequest, RunStatus, utc_now
from backend.tests.helpers import make_manager, make_settings
from backend.tests.test_api import client_for


async def test_four_runs_complete_and_fifth_is_rejected_within_one_second() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=20,
        generator_delay=0.005,
        reviewer_delay=0.05,
    )
    app = create_app(
        settings=make_settings(max_concurrent_runs=4),
        provider=provider,
    )
    payload = {
        "user_idea": "Build a concurrent podcast product with isolated state.",
        "quality_threshold": 70,
        "max_iterations": 1,
    }

    async with await client_for(app) as client:
        accepted = await asyncio.gather(
            *[client.post("/api/runs", json=payload) for _ in range(4)]
        )
        started = monotonic()
        rejected = await client.post("/api/runs", json=payload)
        rejection_seconds = monotonic() - started
        results = await asyncio.gather(
            *[
                app.state.manager.wait_for_completion(
                    UUID(response.json()["run_id"]),
                    wait_seconds=5,
                )
                for response in accepted
            ]
        )

    assert all(response.status_code == 202 for response in accepted)
    assert rejected.status_code == 429
    assert rejected.json()["error"]["code"] == "RUN_CAPACITY_REACHED"
    assert rejection_seconds < 1
    assert all(result.status is RunStatus.COMPLETED for result in results)
    assert len({result.run_id for result in results}) == 4


async def test_event_buffer_is_bounded_and_two_cleanup_cycles_remove_all_refs() -> None:
    manager = make_manager(
        settings=make_settings(event_buffer_size=10, run_ttl_seconds=60)
    )
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a resource lifecycle validation product.",
            quality_threshold=70,
            max_iterations=1,
        )
    )
    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)
    assert result.status is RunStatus.COMPLETED
    assert manager.event_store.buffer_length(created.run_id) <= 10
    assert created.run_id not in manager.tasks

    manager.run_store._now = lambda: utc_now() + timedelta(seconds=61)
    first = await manager.cleanup_once()
    second = await manager.cleanup_once()

    assert first == [created.run_id]
    assert second == []
    assert await manager.run_store.count() == 0
    assert created.run_id not in manager.event_store._events
    assert created.run_id not in manager.event_store._conditions
    assert created.run_id not in manager.cancel_signals
    assert created.run_id not in manager.resume_signals
    assert created.run_id not in manager.tasks


async def test_long_prd_stream_is_exact_and_not_duplicated() -> None:
    provider = MockLLMProvider(
        delays_enabled=False,
        chunk_size=7,
    )
    manager = make_manager(
        provider=provider,
        settings=make_settings(event_buffer_size=100),
    )
    idea = "L" * 5000
    expected = provider._prd(idea, None, None, 1, None)
    created = await manager.create_run(
        CreateRunRequest(
            user_idea=idea,
            quality_threshold=70,
            max_iterations=1,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert result.versions[0].content == expected
    assert result.current_prd == expected
    assert manager.event_store.buffer_length(created.run_id) <= 100
