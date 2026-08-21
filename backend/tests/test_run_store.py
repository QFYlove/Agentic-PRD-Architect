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


async def _seed_terminal_runs(
    database_path: str,
    *,
    count: int,
    max_runs: int,
) -> list[RunSnapshot]:
    store = SQLiteRunStore(
        database_path=database_path,
        max_runs=max_runs,
        ttl_seconds=2_592_000,
    )
    created: list[RunSnapshot] = []
    base = datetime(2026, 7, 26, tzinfo=UTC)
    for index in range(count):
        snap = snapshot(RunStatus.COMPLETED)
        snap.updated_at = base + timedelta(minutes=index)
        await store.create(snap)
        await store.save_unlocked(snap.run_id)
        created.append(snap)
    await store.close()
    return created


async def test_sqlite_store_trims_overflowing_history_on_load(tmp_path: Path) -> None:
    """A database over the cap must not wedge run creation until the TTL."""
    database_path = str(tmp_path / "retention.sqlite3")
    created = await _seed_terminal_runs(database_path, count=6, max_runs=10)

    restored = SQLiteRunStore(
        database_path=database_path,
        max_runs=4,
        ttl_seconds=2_592_000,
    )

    assert await restored.count() == 4
    surviving = set(await restored.run_ids())
    # The two oldest terminal runs are dropped; the newest four survive.
    assert surviving == {snap.run_id for snap in created[2:]}
    rows = restored._connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    assert rows == 4

    fresh = snapshot()
    assert await restored.make_room() == [created[2].run_id]
    await restored.create(fresh)
    assert (await restored.get(fresh.run_id)).status is RunStatus.QUEUED
    await restored.close()


async def test_make_room_evicts_oldest_terminal_run_and_spares_active(
    tmp_path: Path,
) -> None:
    database_path = str(tmp_path / "make-room.sqlite3")
    store = SQLiteRunStore(
        database_path=database_path,
        max_runs=3,
        ttl_seconds=2_592_000,
    )
    base = datetime(2026, 7, 26, tzinfo=UTC)
    oldest_terminal = snapshot(RunStatus.COMPLETED)
    oldest_terminal.updated_at = base
    newer_terminal = snapshot(RunStatus.FAILED)
    newer_terminal.updated_at = base + timedelta(minutes=5)
    active = snapshot(RunStatus.GENERATING)
    active.updated_at = base - timedelta(days=1)
    for snap in (oldest_terminal, newer_terminal, active):
        await store.create(snap)
        await store.save_unlocked(snap.run_id)

    evicted = await store.make_room()

    # The active run is the oldest by timestamp but must never be evicted.
    assert evicted == [oldest_terminal.run_id]
    assert set(await store.run_ids()) == {newer_terminal.run_id, active.run_id}
    assert (await store.get(active.run_id)).status is RunStatus.GENERATING
    remaining = {
        row[0]
        for row in store._connection.execute("SELECT run_id FROM runs").fetchall()
    }
    assert remaining == {str(newer_terminal.run_id), str(active.run_id)}
    await store.close()


async def test_make_room_is_a_noop_when_only_active_runs_fill_the_cap(
    tmp_path: Path,
) -> None:
    """With nothing evictable, capacity is still enforced by create()."""
    store = SQLiteRunStore(
        database_path=str(tmp_path / "all-active.sqlite3"),
        max_runs=2,
        ttl_seconds=2_592_000,
    )
    for _ in range(2):
        snap = snapshot(RunStatus.GENERATING)
        await store.create(snap)

    assert await store.make_room() == []
    assert await store.count() == 2
    with pytest.raises(StoreCapacityError):
        await store.create(snapshot())
    await store.close()


async def test_load_keeps_all_runs_when_history_fits_under_the_cap(
    tmp_path: Path,
) -> None:
    database_path = str(tmp_path / "under-cap.sqlite3")
    created = await _seed_terminal_runs(database_path, count=3, max_runs=10)

    restored = SQLiteRunStore(
        database_path=database_path,
        max_runs=10,
        ttl_seconds=2_592_000,
    )

    assert set(await restored.run_ids()) == {snap.run_id for snap in created}
    assert await restored.make_room() == []
    await restored.close()
