from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from backend.errors import StoreCapacityError
from backend.run_store import InMemoryRunStore, SQLiteRunStore
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


async def test_sqlite_store_persists_snapshots_and_lists_recent_runs(
    tmp_path: Path,
) -> None:
    database_path = str(tmp_path / "runs.sqlite3")
    store = SQLiteRunStore(
        database_path=database_path,
        max_runs=5,
        ttl_seconds=60,
    )
    original = snapshot(RunStatus.COMPLETED)
    original.current_prd = "persisted PRD"
    await store.create(original)
    await store.close()

    restored = SQLiteRunStore(
        database_path=database_path,
        max_runs=5,
        ttl_seconds=60,
    )

    assert (await restored.get(original.run_id)).current_prd == "persisted PRD"
    summaries = await restored.list_runs(limit=10)
    assert [item.run_id for item in summaries] == [original.run_id]
    await restored.close()


async def test_sqlite_store_marks_interrupted_runs_failed(tmp_path: Path) -> None:
    database_path = str(tmp_path / "interrupted.sqlite3")
    store = SQLiteRunStore(
        database_path=database_path,
        max_runs=5,
        ttl_seconds=60,
    )
    active = snapshot(RunStatus.GENERATING)
    active.active_node = "generator"
    await store.create(active)
    await store.close()

    restored = SQLiteRunStore(
        database_path=database_path,
        max_runs=5,
        ttl_seconds=60,
    )
    recovered = await restored.get(active.run_id)

    assert recovered.status is RunStatus.FAILED
    assert recovered.error is not None
    assert recovered.error.code == "RUN_INTERRUPTED"
    assert recovered.active_node is None
    await restored.close()
