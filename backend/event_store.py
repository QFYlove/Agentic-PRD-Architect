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
    """Replayable events persisted to the same local SQLite database."""

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
        for run_id, sequence in initial_sequences.items():
            self._events[run_id] = deque(maxlen=self.buffer_size)
            self._sequences[run_id] = sequence
            self._conditions[run_id] = asyncio.Condition()
        rows = self._connection.execute(
            "SELECT run_id, event_json FROM run_events ORDER BY run_id, sequence"
        ).fetchall()
        for run_id_value, event_json in rows:
            run_id = UUID(run_id_value)
            if run_id not in self._events:
                continue
            event = RunEvent.model_validate_json(event_json)
            self._events[run_id].append(event)
            self._sequences[run_id] = max(
                self._sequences[run_id],
                event.sequence,
            )

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

    def remove_run(self, run_id: UUID) -> None:
        super().remove_run(run_id)
        self._connection.execute(
            "DELETE FROM run_events WHERE run_id = ?",
            (str(run_id),),
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()
