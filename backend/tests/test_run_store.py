from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from backend.errors import StoreCapacityError
from backend.run_store import InMemoryRunStore
from backend.schemas import RunSnapshot, RunStatus


def snapshot(status: RunStatus = RunStatus.QUEUED) -> RunSnapshot:
    return RunSnapshot(
        run_id=uuid4(),
        user_idea="A sufficiently detailed product idea.",
        status=status,
    )


async def test_store_copies_snapshots_and_enforces_capacity() -> None:
    store = InMemoryRunStore(max_runs=1, ttl_seconds=60)
    original = snapshot()
    await store.create(original)

    loaded = await store.get(original.run_id)
    loaded.current_prd = "mutated outside store"

    assert (await store.get(original.run_id)).current_prd == ""
    with pytest.raises(StoreCapacityError):
        await store.create(snapshot())


async def test_store_cleanup_only_removes_expired_terminal_runs() -> None:
    now = datetime(2026, 7, 26, tzinfo=UTC)
    clock = [now]
    store = InMemoryRunStore(
        max_runs=5,
        ttl_seconds=60,
        now=lambda: clock[0],
    )
    completed = snapshot(RunStatus.COMPLETED)
    active = snapshot(RunStatus.PAUSED)
    completed.updated_at = now
    active.updated_at = now
    await store.create(completed)
    await store.create(active)
    clock[0] += timedelta(seconds=61)

    expired = await store.cleanup_expired()

    assert expired == [completed.run_id]
    assert (await store.get(active.run_id)).status is RunStatus.PAUSED
