"""prd_delta is a live-only event: streamed to subscribers, never persisted.

These tests run the full mock workflow against the real SQLite stores (the ones
`create_app` wires) because `make_manager` uses in-memory stores, which cannot
show write amplification at all.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from backend import event_store, run_manager
from backend.run_store import SQLiteRunStore
from backend.schemas import CreateRunRequest, RunEventType, RunSnapshot, RunStatus
from backend.tests.helpers import make_settings, make_sqlite_manager


def count_persist_calls(store: SQLiteRunStore) -> list[int]:
    """Replace `_persist` with a counting passthrough; returns a 1-slot counter."""
    counter = [0]
    original = store._persist

    def counting(snapshot: RunSnapshot) -> None:
        counter[0] += 1
        original(snapshot)

    store._persist = counting  # type: ignore[method-assign]
    return counter


def event_counts(store: Any, run_id: UUID) -> dict[str, int]:
    rows = store._connection.execute(
        """
        SELECT json_extract(event_json, '$.event') AS event, COUNT(*)
        FROM run_events WHERE run_id = ? GROUP BY event
        """,
        (str(run_id),),
    ).fetchall()
    return {event: count for event, count in rows}


async def measure_run(
    database_path: str,
) -> tuple[int, int, dict[str, int]]:
    """Run one full mock workflow; return (persists, live deltas, event rows)."""
    manager = make_sqlite_manager(database_path=database_path)
    store = manager.run_store
    assert isinstance(store, SQLiteRunStore)
    persists = count_persist_calls(store)

    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a delta persistence product.")
    )
    result = await manager.wait_for_completion(created.run_id, wait_seconds=10)
    assert result.status is RunStatus.COMPLETED

    deltas = sum(
        1
        for event in manager.event_store.replay(created.run_id, 0)
        if event.event is RunEventType.PRD_DELTA
    )
    rows = event_counts(manager.event_store, created.run_id)
    manager.event_store.close()
    await store.close()
    return persists[0], deltas, rows


async def test_full_generation_persists_no_deltas_and_no_per_delta_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same workflow, with and without delta transience, side by side."""
    after_persists, after_deltas, after_rows = await measure_run(
        str(tmp_path / "after.sqlite3")
    )

    # Restore the pre-change behaviour: nothing is transient, so every delta is
    # both an INSERT and a full snapshot rewrite.
    monkeypatch.setattr(event_store, "TRANSIENT_EVENT_TYPES", frozenset())
    monkeypatch.setattr(run_manager, "TRANSIENT_EVENT_TYPES", frozenset())
    before_persists, before_deltas, before_rows = await measure_run(
        str(tmp_path / "before.sqlite3")
    )

    assert after_deltas == before_deltas > 0
    # Deltas still stream live, but they no longer reach SQLite at all.
    assert before_rows[RunEventType.PRD_DELTA.value] == before_deltas
    assert RunEventType.PRD_DELTA.value not in after_rows
    assert after_rows[RunEventType.PRD_GENERATED.value] >= 1
    # Exactly one snapshot rewrite per delta disappeared -- nothing else moved.
    assert before_persists - after_persists == before_deltas
    assert sum(before_rows.values()) - sum(after_rows.values()) == before_deltas


async def test_prd_generated_boundary_persists_the_full_prd(tmp_path: Path) -> None:
    """A reconnecting client is calibrated by the snapshot, so it must be current."""
    database_path = str(tmp_path / "boundary.sqlite3")
    manager = make_sqlite_manager(database_path=database_path)
    store = manager.run_store
    assert isinstance(store, SQLiteRunStore)

    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a durable boundary product.")
    )
    seen_prd: str | None = None
    async for event in manager.stream_events(created.run_id, after_sequence=0):
        if event is not None and event.event is RunEventType.PRD_GENERATED:
            # Read the row SQLite holds right now, bypassing the in-memory copy.
            row = store._connection.execute(
                "SELECT snapshot_json FROM runs WHERE run_id = ?",
                (str(created.run_id),),
            ).fetchone()
            seen_prd = RunSnapshot.model_validate_json(row[0]).current_prd
            break

    assert seen_prd is not None
    assert len(seen_prd) > 0
    assert seen_prd == str(event.payload["content"])
    await manager.wait_for_completion(created.run_id, wait_seconds=10)
    manager.event_store.close()
    await store.close()


async def test_completed_prd_and_replay_survive_restart_without_deltas(
    tmp_path: Path,
) -> None:
    database_path = str(tmp_path / "restart.sqlite3")
    manager = make_sqlite_manager(database_path=database_path)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a restart recovery product.")
    )
    completed = await manager.wait_for_completion(created.run_id, wait_seconds=10)
    assert completed.status is RunStatus.COMPLETED
    live_sequences = [
        event.sequence for event in manager.event_store.replay(created.run_id, 0)
    ]
    manager.event_store.close()
    await manager.run_store.close()

    restored = make_sqlite_manager(database_path=database_path)
    recovered = await restored.get_run(created.run_id)

    # Snapshot recovery, not delta replay, is what carries the PRD across restart.
    assert recovered.status is RunStatus.COMPLETED
    assert recovered.current_prd == completed.current_prd
    assert recovered.versions[-1].content == completed.versions[-1].content
    replayed = [
        event.sequence for event in restored.event_store.replay(created.run_id, 0)
    ]
    assert replayed == sorted(set(replayed))
    assert set(replayed).issubset(set(live_sequences))
    assert RunEventType.PRD_GENERATED.value in event_counts(
        restored.event_store, created.run_id
    )
    restored.event_store.close()
    await restored.run_store.close()


async def test_live_subscriber_receives_deltas_that_sqlite_never_stores(
    tmp_path: Path,
) -> None:
    database_path = str(tmp_path / "live.sqlite3")
    manager = make_sqlite_manager(
        database_path=database_path,
        settings=make_settings(database_path=database_path, event_buffer_size=10),
    )
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a live streaming product.")
    )
    received: list[RunEventType] = []

    async def reader() -> None:
        async for event in manager.stream_events(created.run_id, after_sequence=0):
            if event is not None:
                received.append(event.event)

    task = asyncio.create_task(reader())
    await manager.wait_for_completion(created.run_id, wait_seconds=10)
    await manager.event_store.wake(created.run_id)
    await asyncio.wait_for(task, timeout=5)

    # A buffer of 10 cannot hold the whole run, so these deltas were delivered
    # live rather than replayed -- and they exist nowhere in SQLite.
    assert received.count(RunEventType.PRD_DELTA) > 0
    assert RunEventType.PRD_DELTA.value not in event_counts(
        manager.event_store, created.run_id
    )
    manager.event_store.close()
    await manager.run_store.close()


async def test_severity_counts_survive_a_restart_unchanged(tmp_path: Path) -> None:
    """A reopened run has to report the numbers it reported while it was live.

    The counts are derived from the stored feedback rather than persisted as
    totals, so this is what proves the derivation still holds after the snapshot
    has been through JSON and back: the same 21 findings, split the same way.
    """
    database_path = str(tmp_path / "severity.sqlite3")
    manager = make_sqlite_manager(database_path=database_path)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a durable severity accounting product.")
    )
    completed = await manager.wait_for_completion(created.run_id, wait_seconds=10)
    assert completed.latest_evaluation is not None
    live_counts = completed.latest_evaluation.severity_counts()
    live_items = len(completed.latest_evaluation.combined_feedback)
    manager.event_store.close()
    await manager.run_store.close()

    restored = make_sqlite_manager(database_path=database_path)
    recovered = await restored.get_run(created.run_id)

    assert recovered.latest_evaluation is not None
    assert recovered.latest_evaluation.severity_counts() == live_counts
    assert len(recovered.latest_evaluation.combined_feedback) == live_items
    # The final version carries the same evaluation, which is what a reconnecting
    # client falls back to when `latest_evaluation` is absent.
    final = recovered.versions[-1].evaluation
    assert final is not None
    assert final.severity_counts() == live_counts
    # Every stored item is structured, so no tier can be silently coerced.
    assert all(
        item.severity.value in {"must_fix", "should_fix", "optional"}
        for item in recovered.latest_evaluation.combined_feedback
    )
    restored.event_store.close()
    await restored.run_store.close()
