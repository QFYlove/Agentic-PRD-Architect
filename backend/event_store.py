from __future__ import annotations

import asyncio
import sqlite3
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.errors import EventExpiredError, RunNotFoundError
from backend.schemas import RunEvent, RunEventType

TRANSIENT_EVENT_TYPES = frozenset({RunEventType.PRD_DELTA})
"""Events that are streamed live but never persisted.

``prd_delta`` carries a 128-character slice of a PRD that ``prd_generated``
republishes in full at the end of the same generation, so persisting deltas
costs ~96% of all event rows while adding no recoverable state. Delta events
still enter the in-memory buffer, so an attached SSE client receives them in
real time; a client that reconnects after they have been evicted or after a
restart is calibrated by the snapshot plus the durable ``prd_generated`` event.
"""


class EventStore:
    def __init__(self, *, buffer_size: int, heartbeat_seconds: float) -> None:
        self.buffer_size = buffer_size
        self.heartbeat_seconds = heartbeat_seconds
        self._events: dict[UUID, deque[RunEvent]] = {}
        self._sequences: dict[UUID, int] = {}
        self._conditions: dict[UUID, asyncio.Condition] = {}

    def create_run(self, run_id: UUID) -> None:
        if run_id in self._events:
            raise ValueError(f"Event stream already exists: {run_id}")
        self._events[run_id] = deque(maxlen=self.buffer_size)
        self._sequences[run_id] = 0
        self._conditions[run_id] = asyncio.Condition()

    def latest_sequence(self, run_id: UUID) -> int:
        try:
            return self._sequences[run_id]
        except KeyError as exc:
            raise RunNotFoundError from exc

    async def append(
        self,
        *,
        run_id: UUID,
        event: RunEventType,
        iteration: int,
        payload: dict[str, Any],
    ) -> RunEvent:
        try:
            condition = self._conditions[run_id]
        except KeyError as exc:
            raise RunNotFoundError from exc
        async with condition:
            sequence = self._sequences[run_id] + 1
            envelope = RunEvent(
                run_id=run_id,
                sequence=sequence,
                event=event,
                iteration=iteration,
                payload=payload,
            )
            self._events[run_id].append(envelope)
            self._sequences[run_id] = sequence
            condition.notify_all()
            return envelope.model_copy(deep=True)

    def replay(self, run_id: UUID, after_sequence: int) -> list[RunEvent]:
        try:
            events = self._events[run_id]
        except KeyError as exc:
            raise RunNotFoundError from exc
        if events and after_sequence < events[0].sequence - 1:
            raise EventExpiredError(events[0].sequence)
        return [
            event.model_copy(deep=True)
            for event in events
            if event.sequence > after_sequence
        ]

    async def subscribe(
        self,
        run_id: UUID,
        *,
        after_sequence: int,
        is_terminal: Callable[[], Awaitable[bool]],
    ) -> AsyncIterator[RunEvent | None]:
        try:
            condition = self._conditions[run_id]
        except KeyError as exc:
            raise RunNotFoundError from exc
        cursor = after_sequence
        while True:
            pending = self.replay(run_id, cursor)
            if pending:
                for event in pending:
                    cursor = event.sequence
                    yield event
                continue
            if await is_terminal():
                return
            heartbeat = False
            async with condition:
                pending = self.replay(run_id, cursor)
                if pending:
                    continue
                try:
                    await asyncio.wait_for(
                        condition.wait(),
                        timeout=self.heartbeat_seconds,
                    )
                except TimeoutError:
                    heartbeat = True
            if heartbeat:
                if await is_terminal():
                    return
                yield None

    async def wake(self, run_id: UUID) -> None:
        condition = self._conditions.get(run_id)
        if condition is None:
            return
        async with condition:
            condition.notify_all()

    def remove_run(self, run_id: UUID) -> None:
        self._events.pop(run_id, None)
        self._sequences.pop(run_id, None)
        self._conditions.pop(run_id, None)

    def buffer_length(self, run_id: UUID) -> int:
        try:
            return len(self._events[run_id])
        except KeyError as exc:
            raise RunNotFoundError from exc

    def close(self) -> None:
        return None


class SQLiteEventStore(EventStore):
    """Replayable events persisted to the same local SQLite database.

    SQLite is the source of truth for replay; the in-memory deque is only a hot
    cache for the newest ``buffer_size`` events. ``initial_sequences`` must
    enumerate every retained run: events belonging to any other run are treated
    as orphans and deleted on startup.
    """

    def __init__(
        self,
        *,
        database_path: str,
        buffer_size: int,
        heartbeat_seconds: float,
        initial_sequences: dict[UUID, int],
    ) -> None:
        super().__init__(
            buffer_size=buffer_size,
            heartbeat_seconds=heartbeat_seconds,
        )
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, timeout=5)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS run_events (
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence)
            )
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_run_events_replay
            ON run_events(run_id, sequence)
            """
        )
        self._connection.commit()
        self._adopt_retained_runs(initial_sequences)

    def _adopt_retained_runs(self, initial_sequences: dict[UUID, int]) -> None:
        """Register retained runs and drop events left behind by evicted runs."""
        for run_id, sequence in initial_sequences.items():
            self._events[run_id] = deque(maxlen=self.buffer_size)
            self._sequences[run_id] = sequence
            self._conditions[run_id] = asyncio.Condition()
        orphans = [
            run_id_value
            for (run_id_value,) in self._connection.execute(
                "SELECT DISTINCT run_id FROM run_events"
            ).fetchall()
            if UUID(run_id_value) not in self._events
        ]
        if orphans:
            self._connection.executemany(
                "DELETE FROM run_events WHERE run_id = ?",
                [(run_id_value,) for run_id_value in orphans],
            )
            self._connection.commit()
        for run_id in self._events:
            self._warm_cache(run_id)

    def _warm_cache(self, run_id: UUID) -> None:
        """Fill the hot cache with the newest persisted events for one run."""
        rows = self._connection.execute(
            """
            SELECT event_json FROM run_events
            WHERE run_id = ?
            ORDER BY sequence DESC
            LIMIT ?
            """,
            (str(run_id), self.buffer_size),
        ).fetchall()
        for (event_json,) in reversed(rows):
            event = RunEvent.model_validate_json(event_json)
            self._events[run_id].append(event)
            self._sequences[run_id] = max(self._sequences[run_id], event.sequence)

    async def append(
        self,
        *,
        run_id: UUID,
        event: RunEventType,
        iteration: int,
        payload: dict[str, Any],
    ) -> RunEvent:
        envelope = await super().append(
            run_id=run_id,
            event=event,
            iteration=iteration,
            payload=payload,
        )
        if event in TRANSIENT_EVENT_TYPES:
            # Live subscribers already have it from the in-memory buffer; the
            # sequence number is still consumed so ordering stays monotonic.
            return envelope
        self._connection.execute(
            """
            INSERT INTO run_events (run_id, sequence, event_json)
            VALUES (?, ?, ?)
            """,
            (
                str(run_id),
                envelope.sequence,
                envelope.model_dump_json(),
            ),
        )
        self._connection.commit()
        return envelope

    def replay(self, run_id: UUID, after_sequence: int) -> list[RunEvent]:
        """Replay persisted events, not just the ones still in the hot cache.

        The in-memory deque is bounded by ``buffer_size``, so it cannot answer
        reconnects for long runs or for anything that predates a restart. SQLite
        retains every durable event for a retained run, so it is the replay
        source of truth; ``EventExpiredError`` is raised only when the requested
        range was genuinely dropped from the database.

        Transient events (see ``TRANSIENT_EVENT_TYPES``) are served only while
        they remain in the hot cache. Falling back to SQLite therefore yields a
        sequence with gaps where deltas were skipped -- clients must treat
        sequence numbers as ordering, not as a dense count, and calibrate PRD
        text from the snapshot plus the durable ``prd_generated`` event.
        """
        if run_id not in self._events:
            raise RunNotFoundError
        cached = self._events[run_id]
        if cached and after_sequence >= cached[0].sequence - 1:
            # The deque holds a contiguous suffix, so it already covers the
            # whole requested range, transient events included.
            return [
                event.model_copy(deep=True)
                for event in cached
                if event.sequence > after_sequence
            ]
        oldest = self._connection.execute(
            "SELECT MIN(sequence) FROM run_events WHERE run_id = ?",
            (str(run_id),),
        ).fetchone()[0]
        if oldest is not None and after_sequence < oldest - 1:
            raise EventExpiredError(int(oldest))
        rows = self._connection.execute(
            """
            SELECT event_json FROM run_events
            WHERE run_id = ? AND sequence > ?
            ORDER BY sequence
            """,
            (str(run_id), after_sequence),
        ).fetchall()
        return [RunEvent.model_validate_json(event_json) for (event_json,) in rows]

    def remove_run(self, run_id: UUID) -> None:
        super().remove_run(run_id)
        self._connection.execute(
            "DELETE FROM run_events WHERE run_id = ?",
            (str(run_id),),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
