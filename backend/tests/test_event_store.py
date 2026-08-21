from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from backend.errors import EventExpiredError, RunNotFoundError
from backend.event_store import EventStore, SQLiteEventStore
from backend.schemas import RunEventType


async def test_event_sequences_replay_and_buffer_expiration() -> None:
    store = EventStore(buffer_size=3, heartbeat_seconds=0.01)
    run_id = uuid4()
    store.create_run(run_id)

    for index in range(5):
        await store.append(
            run_id=run_id,
            event=RunEventType.STATUS_CHANGED,
            iteration=1,
            payload={"index": index},
        )

    assert [event.sequence for event in store.replay(run_id, 3)] == [4, 5]
    assert store.buffer_length(run_id) == 3
    with pytest.raises(EventExpiredError):
        store.replay(run_id, 0)


async def test_concurrent_appends_keep_unique_strict_sequence() -> None:
    store = EventStore(buffer_size=100, heartbeat_seconds=1)
    run_id = uuid4()
    store.create_run(run_id)

    events = await asyncio.gather(
        *[
            store.append(
                run_id=run_id,
                event=RunEventType.STATUS_CHANGED,
                iteration=1,
                payload={"worker": index},
            )
            for index in range(50)
        ]
    )

    assert sorted(event.sequence for event in events) == list(range(1, 51))
    assert [event.sequence for event in store.replay(run_id, 0)] == list(range(1, 51))


async def test_subscription_wakes_all_subscribers() -> None:
    store = EventStore(buffer_size=10, heartbeat_seconds=1)
    run_id = uuid4()
    store.create_run(run_id)
    terminal = False

    async def is_terminal() -> bool:
        return terminal

    async def read_one() -> int:
        async for event in store.subscribe(
            run_id,
            after_sequence=0,
            is_terminal=is_terminal,
        ):
            if event is not None:
                return event.sequence
        raise AssertionError("subscription ended without an event")

    readers = [asyncio.create_task(read_one()) for _ in range(2)]
    await asyncio.sleep(0)
    await store.append(
        run_id=run_id,
        event=RunEventType.RUN_STARTED,
        iteration=1,
        payload={},
    )

    assert await asyncio.gather(*readers) == [1, 1]


async def test_heartbeat_is_not_buffered_or_sequenced() -> None:
    store = EventStore(buffer_size=10, heartbeat_seconds=0.01)
    run_id = uuid4()
    store.create_run(run_id)

    async def is_terminal() -> bool:
        return False

    stream = store.subscribe(run_id, after_sequence=0, is_terminal=is_terminal)
    heartbeat = await anext(stream)
    await stream.aclose()

    assert heartbeat is None
    assert store.latest_sequence(run_id) == 0
    assert store.buffer_length(run_id) == 0


async def test_sqlite_events_replay_after_reopen(tmp_path: Path) -> None:
    database_path = str(tmp_path / "events.sqlite3")
    run_id = uuid4()
    store = SQLiteEventStore(
        database_path=database_path,
        buffer_size=10,
        heartbeat_seconds=1,
        initial_sequences={},
    )
    store.create_run(run_id)
    event = await store.append(
        run_id=run_id,
        event=RunEventType.RUN_STARTED,
        iteration=1,
        payload={"persisted": True},
    )
    store.close()

    restored = SQLiteEventStore(
        database_path=database_path,
        buffer_size=10,
        heartbeat_seconds=1,
        initial_sequences={run_id: event.sequence},
    )

    replayed = restored.replay(run_id, 0)
    assert len(replayed) == 1
    assert replayed[0].payload == {"persisted": True}
    restored.close()


async def test_sqlite_replay_survives_hot_cache_overflow(tmp_path: Path) -> None:
    """Events evicted from the bounded deque must still replay from SQLite."""
    run_id = uuid4()
    store = SQLiteEventStore(
        database_path=str(tmp_path / "overflow.sqlite3"),
        buffer_size=5,
        heartbeat_seconds=1,
        initial_sequences={},
    )
    store.create_run(run_id)
    for index in range(20):
        await store.append(
            run_id=run_id,
            event=RunEventType.STATUS_CHANGED,
            iteration=1,
            payload={"index": index},
        )

    assert store.buffer_length(run_id) == 5
    full = store.replay(run_id, 0)
    assert [event.sequence for event in full] == list(range(1, 21))
    assert full[0].payload == {"index": 0}
    assert [event.sequence for event in store.replay(run_id, 12)] == list(range(13, 21))
    assert store.replay(run_id, 20) == []
    store.close()


async def test_sqlite_replay_after_restart_returns_pre_restart_events(
    tmp_path: Path,
) -> None:
    """A reconnect with an old Last-Event-ID must not be rejected after restart."""
    database_path = str(tmp_path / "restart.sqlite3")
    run_id = uuid4()
    store = SQLiteEventStore(
        database_path=database_path,
        buffer_size=5,
        heartbeat_seconds=1,
        initial_sequences={},
    )
    store.create_run(run_id)
    for index in range(20):
        await store.append(
            run_id=run_id,
            event=RunEventType.STATUS_CHANGED,
            iteration=1,
            payload={"index": index},
        )
    store.close()

    restored = SQLiteEventStore(
        database_path=database_path,
        buffer_size=5,
        heartbeat_seconds=1,
        initial_sequences={run_id: 20},
    )

    assert restored.latest_sequence(run_id) == 20
    assert restored.buffer_length(run_id) == 5
    replayed = restored.replay(run_id, 0)
    assert [event.sequence for event in replayed] == list(range(1, 21))
    assert replayed[0].payload == {"index": 0}
    appended = await restored.append(
        run_id=run_id,
        event=RunEventType.RUN_COMPLETED,
        iteration=1,
        payload={},
    )
    assert appended.sequence == 21
    restored.close()


async def test_sqlite_replay_expires_only_genuinely_deleted_ranges(
    tmp_path: Path,
) -> None:
    run_id = uuid4()
    store = SQLiteEventStore(
        database_path=str(tmp_path / "expired.sqlite3"),
        buffer_size=2,
        heartbeat_seconds=1,
        initial_sequences={},
    )
    store.create_run(run_id)
    for index in range(6):
        await store.append(
            run_id=run_id,
            event=RunEventType.STATUS_CHANGED,
            iteration=1,
            payload={"index": index},
        )
    # Nothing was deleted, so even the very first cursor still replays.
    assert len(store.replay(run_id, 0)) == 6

    store._connection.execute(
        "DELETE FROM run_events WHERE run_id = ? AND sequence <= 3",
        (str(run_id),),
    )
    store._connection.commit()

    with pytest.raises(EventExpiredError) as excinfo:
        store.replay(run_id, 0)
    assert "4" in excinfo.value.message
    assert [event.sequence for event in store.replay(run_id, 3)] == [4, 5, 6]
    with pytest.raises(RunNotFoundError):
        store.replay(uuid4(), 0)
    store.close()


async def test_sqlite_terminal_run_replay_is_unaffected_by_removal_of_others(
    tmp_path: Path,
) -> None:
    """Evicting one run must not disturb replay for a retained run."""
    database_path = str(tmp_path / "isolation.sqlite3")
    kept = uuid4()
    dropped = uuid4()
    store = SQLiteEventStore(
        database_path=database_path,
        buffer_size=2,
        heartbeat_seconds=1,
        initial_sequences={},
    )
    for run_id in (kept, dropped):
        store.create_run(run_id)
        for index in range(6):
            await store.append(
                run_id=run_id,
                event=RunEventType.STATUS_CHANGED,
                iteration=1,
                payload={"index": index},
            )

    store.remove_run(dropped)

    assert [event.sequence for event in store.replay(kept, 0)] == [1, 2, 3, 4, 5, 6]
    assert (
        store._connection.execute(
            "SELECT COUNT(*) FROM run_events WHERE run_id = ?",
            (str(dropped),),
        ).fetchone()[0]
        == 0
    )
    store.close()


async def test_sqlite_startup_deletes_events_of_unretained_runs(
    tmp_path: Path,
) -> None:
    """Runs evicted by retention must not leave orphaned event rows behind."""
    database_path = str(tmp_path / "orphans.sqlite3")
    kept = uuid4()
    evicted = uuid4()
    store = SQLiteEventStore(
        database_path=database_path,
        buffer_size=10,
        heartbeat_seconds=1,
        initial_sequences={},
    )
    for run_id in (kept, evicted):
        store.create_run(run_id)
        await store.append(
            run_id=run_id,
            event=RunEventType.RUN_STARTED,
            iteration=1,
            payload={},
        )
    store.close()

    # The run store dropped `evicted`, so it is absent from initial_sequences.
    restored = SQLiteEventStore(
        database_path=database_path,
        buffer_size=10,
        heartbeat_seconds=1,
        initial_sequences={kept: 1},
    )

    assert len(restored.replay(kept, 0)) == 1
    assert (
        restored._connection.execute("SELECT COUNT(*) FROM run_events").fetchone()[0]
        == 1
    )
    with pytest.raises(RunNotFoundError):
        restored.replay(evicted, 0)
    restored.close()


async def test_prd_delta_streams_live_but_is_never_persisted(tmp_path: Path) -> None:
    """Deltas reach attached subscribers yet leave no row in `run_events`."""
    database_path = str(tmp_path / "transient.sqlite3")
    run_id = uuid4()
    store = SQLiteEventStore(
        database_path=database_path,
        buffer_size=10,
        heartbeat_seconds=1,
        initial_sequences={},
    )
    store.create_run(run_id)
    terminal = False

    async def is_terminal() -> bool:
        return terminal

    received: list[RunEventType] = []
    delivered = asyncio.Event()

    async def reader() -> None:
        async for event in store.subscribe(
            run_id,
            after_sequence=0,
            is_terminal=is_terminal,
        ):
            if event is not None:
                received.append(event.event)
                if len(received) == 5:
                    delivered.set()

    task = asyncio.create_task(reader())
    await asyncio.sleep(0)
    for index in range(4):
        await store.append(
            run_id=run_id,
            event=RunEventType.PRD_DELTA,
            iteration=1,
            payload={"delta": f"chunk-{index}"},
        )
    await store.append(
        run_id=run_id,
        event=RunEventType.PRD_GENERATED,
        iteration=1,
        payload={"prd": "# PRD"},
    )
    await asyncio.wait_for(delivered.wait(), timeout=1)
    terminal = True
    await store.wake(run_id)
    await asyncio.wait_for(task, timeout=1)

    assert received == [RunEventType.PRD_DELTA] * 4 + [RunEventType.PRD_GENERATED]
    persisted = store._connection.execute(
        """
        SELECT sequence, event_json FROM run_events
        WHERE run_id = ? ORDER BY sequence
        """,
        (str(run_id),),
    ).fetchall()
    assert [sequence for sequence, _ in persisted] == [5]
    assert '"prd_delta"' not in "".join(event_json for _, event_json in persisted)
    store.close()


async def test_transient_events_consume_sequences_without_duplicates(
    tmp_path: Path,
) -> None:
    """Sequences stay strictly increasing and unique across transient appends."""
    database_path = str(tmp_path / "sequences.sqlite3")
    run_id = uuid4()
    store = SQLiteEventStore(
        database_path=database_path,
        buffer_size=100,
        heartbeat_seconds=1,
        initial_sequences={},
    )
    store.create_run(run_id)
    sequences = [
        (
            await store.append(
                run_id=run_id,
                event=(
                    RunEventType.PRD_DELTA if index % 3 else RunEventType.STATUS_CHANGED
                ),
                iteration=1,
                payload={"index": index},
            )
        ).sequence
        for index in range(30)
    ]
    store.close()

    assert sequences == list(range(1, 31))
    restored = SQLiteEventStore(
        database_path=database_path,
        buffer_size=100,
        heartbeat_seconds=1,
        initial_sequences={run_id: 30},
    )
    # Post-restart replay carries gaps where deltas were skipped, but it is
    # still strictly increasing, and the next append continues past 30.
    replayed = [event.sequence for event in restored.replay(run_id, 0)]
    assert replayed == sorted(set(replayed))
    assert replayed == [index for index in range(1, 31) if (index - 1) % 3 == 0]
    following = await restored.append(
        run_id=run_id,
        event=RunEventType.RUN_COMPLETED,
        iteration=1,
        payload={},
    )
    assert following.sequence == 31
    restored.close()
