from __future__ import annotations

import asyncio

import pytest

from backend.errors import (
    RunCapacityError,
    RunConflictError,
    RunNotFoundError,
    StoreCapacityError,
)
from backend.providers.mock import MockLLMProvider
from backend.schemas import CreateRunRequest, RunEventType, RunStatus
from backend.tests.helpers import make_manager, make_settings
from backend.tests.test_workflow import wait_for_status


async def test_commit_serializes_concurrent_updates_without_loss() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=10,
        generator_delay=0.02,
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a concurrent update product.")
    )
    await wait_for_status(manager, created.run_id, {RunStatus.GENERATING})
    await manager.cancel_run(created.run_id)
    await manager.wait_for_completion(created.run_id, wait_seconds=5)

    await asyncio.gather(
        *[
            manager.commit(
                created.run_id,
                lambda state: setattr(
                    state,
                    "current_prd",
                    state.current_prd + "x",
                ),
            )
            for _ in range(50)
        ]
    )

    assert (await manager.get_run(created.run_id)).current_prd.endswith("x" * 50)


async def test_snapshot_sequence_never_skips_committed_state_event() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=10,
        generator_delay=0.02,
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build an atomic snapshot product.")
    )
    await wait_for_status(manager, created.run_id, {RunStatus.GENERATING})

    for index in range(20):
        expected = f"atomic-{index}"
        committed = await manager.commit(
            created.run_id,
            lambda state, value=expected: setattr(state, "active_node", value),
            event=RunEventType.STATUS_CHANGED,
            payload={"marker": expected},
        )
        replayed = manager.event_store.replay(
            created.run_id,
            committed.latest_event_sequence - 1,
        )
        assert replayed[0].payload["marker"] == committed.active_node

    await manager.cancel_run(created.run_id)
    await manager.wait_for_completion(created.run_id, wait_seconds=5)


async def test_duplicate_workflow_start_is_rejected_and_reference_cleans_up() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        generator_delay=0.01,
    )
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a uniquely started workflow.")
    )

    with pytest.raises(RunConflictError, match="active workflow"):
        await manager.start_run(created.run_id)

    await manager.wait_for_completion(created.run_id, wait_seconds=5)
    assert created.run_id not in manager.tasks


async def test_shutdown_cancels_running_paused_and_subscriber_tasks() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=100,
        generator_delay=0.005,
        reviewer_delay=0.1,
    )
    manager = make_manager(provider=provider)
    await manager.start()
    running = await manager.create_run(
        CreateRunRequest(user_idea="Build a running shutdown product.")
    )
    paused = await manager.create_run(
        CreateRunRequest(user_idea="Build a paused shutdown product.")
    )
    await wait_for_status(manager, paused.run_id, {RunStatus.REVIEWING})
    await manager.request_pause(paused.run_id)
    await wait_for_status(manager, paused.run_id, {RunStatus.PAUSED})

    async def consume() -> None:
        async for _ in manager.stream_events(
            running.run_id,
            after_sequence=manager.event_store.latest_sequence(running.run_id),
        ):
            pass

    subscriber = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await manager.shutdown()
    await asyncio.wait_for(subscriber, timeout=1)

    assert manager.tasks == {}
    assert manager._cleanup_task is None


async def test_paused_run_still_consumes_concurrency_slot() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=100,
        generator_delay=0.001,
        reviewer_delay=0.05,
    )
    manager = make_manager(
        provider=provider,
        settings=make_settings(max_concurrent_runs=1),
    )
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a slot-consuming paused run.")
    )
    await wait_for_status(manager, created.run_id, {RunStatus.REVIEWING})
    await manager.request_pause(created.run_id)
    await wait_for_status(manager, created.run_id, {RunStatus.PAUSED})

    with pytest.raises(RunCapacityError):
        await manager.create_run(
            CreateRunRequest(user_idea="Build a second blocked product run.")
        )

    await manager.cancel_run(created.run_id)
    await manager.wait_for_completion(created.run_id, wait_seconds=5)
    replacement = await manager.create_run(
        CreateRunRequest(user_idea="Build a replacement after terminal release.")
    )
    await manager.cancel_run(replacement.run_id)
    await manager.wait_for_completion(replacement.run_id, wait_seconds=5)


async def test_retention_evicts_oldest_terminal_run_instead_of_rejecting() -> None:
    """A full retention cap must evict, not wedge creation at HTTP 429."""
    manager = make_manager(settings=make_settings(max_retained_runs=2))
    first = await manager.create_run(
        CreateRunRequest(user_idea="Build the first retained product run.")
    )
    await manager.wait_for_completion(first.run_id, wait_seconds=5)
    second = await manager.create_run(
        CreateRunRequest(user_idea="Build the second retained product run.")
    )
    await manager.wait_for_completion(second.run_id, wait_seconds=5)

    third = await manager.create_run(
        CreateRunRequest(user_idea="Build the third run that forces eviction.")
    )
    await manager.wait_for_completion(third.run_id, wait_seconds=5)

    assert await manager.run_store.count() == 2
    assert set(await manager.run_store.run_ids()) == {second.run_id, third.run_id}
    with pytest.raises(RunNotFoundError):
        await manager.get_run(first.run_id)
    # Per-run resources of the evicted run are released too.
    assert first.run_id not in manager.cancel_signals
    assert first.run_id not in manager.resume_signals
    with pytest.raises(RunNotFoundError):
        manager.event_store.latest_sequence(first.run_id)
    assert manager.event_store.latest_sequence(third.run_id) > 0
    await manager.shutdown()


async def test_retention_never_evicts_an_active_run() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=100,
        generator_delay=0.001,
        reviewer_delay=0.05,
    )
    manager = make_manager(
        provider=provider,
        settings=make_settings(max_retained_runs=1, max_concurrent_runs=2),
    )
    active = await manager.create_run(
        CreateRunRequest(user_idea="Build a long running paused product run.")
    )
    await wait_for_status(manager, active.run_id, {RunStatus.REVIEWING})
    await manager.request_pause(active.run_id)
    await wait_for_status(manager, active.run_id, {RunStatus.PAUSED})

    # Nothing is evictable, so the retention cap is still enforced by create().
    with pytest.raises(StoreCapacityError):
        await manager.create_run(
            CreateRunRequest(user_idea="Build a run that must not evict the active.")
        )
    assert (await manager.get_run(active.run_id)).status is RunStatus.PAUSED

    await manager.cancel_run(active.run_id)
    await manager.wait_for_completion(active.run_id, wait_seconds=5)
    await manager.shutdown()
