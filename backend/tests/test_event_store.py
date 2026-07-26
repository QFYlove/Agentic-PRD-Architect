from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from backend.errors import EventExpiredError
from backend.event_store import EventStore
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
