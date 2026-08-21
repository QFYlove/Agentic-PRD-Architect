from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from backend.errors import RunNotFoundError, StoreCapacityError
from backend.schemas import (
    NodeStatus,
    RunError,
    RunSnapshot,
    RunStatus,
    RunSummary,
    utc_now,
)
from backend.state_machine import TERMINAL_RUN_STATUSES


class InMemoryRunStore:
    def __init__(
        self,
        *,
        max_runs: int,
        ttl_seconds: int,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.max_runs = max_runs
        self.ttl = timedelta(seconds=ttl_seconds)
        self._now = now or (lambda: datetime.now(UTC))
        self._runs: dict[UUID, RunSnapshot] = {}
        self._locks: dict[UUID, asyncio.Lock] = {}
        self._index_lock = asyncio.Lock()

    async def create(self, snapshot: RunSnapshot) -> None:
        async with self._index_lock:
            if snapshot.run_id in self._runs:
                raise ValueError(f"Run already exists: {snapshot.run_id}")
            if len(self._runs) >= self.max_runs:
                raise StoreCapacityError
            self._runs[snapshot.run_id] = snapshot.model_copy(deep=True)
            self._locks[snapshot.run_id] = asyncio.Lock()

    def lock_for(self, run_id: UUID) -> asyncio.Lock:
        try:
            return self._locks[run_id]
        except KeyError as exc:
            raise RunNotFoundError from exc

    def _evictable_run_ids(self, *, needed: int) -> list[UUID]:
        """Oldest terminal runs first. Active runs are never evictable."""
        terminal = sorted(
            (
                (snapshot.updated_at, run_id)
                for run_id, snapshot in self._runs.items()
                if snapshot.status in TERMINAL_RUN_STATUSES
            ),
        )
        return [run_id for _, run_id in terminal[:needed]]

    async def make_room(self, *, incoming: int = 1) -> list[UUID]:
        """Evict old terminal runs so ``incoming`` new runs fit under the cap.

        Retention must not be able to wedge the service: without this, a
        database holding ``max_runs`` finished runs rejects every new run until
        the TTL elapses. Returns the evicted run ids so the caller can release
        their events and per-run resources.
        """
        async with self._index_lock:
            overflow = len(self._runs) + incoming - self.max_runs
            if overflow <= 0:
                return []
            evicted = self._evictable_run_ids(needed=overflow)
            for run_id in evicted:
                del self._runs[run_id]
                del self._locks[run_id]
            return evicted

    def get_unlocked(self, run_id: UUID) -> RunSnapshot:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise RunNotFoundError from exc

    async def get(self, run_id: UUID) -> RunSnapshot:
        lock = self.lock_for(run_id)
        async with lock:
            return self.get_unlocked(run_id).model_copy(deep=True)

    async def save_unlocked(self, run_id: UUID) -> None:
        self.get_unlocked(run_id)

    async def remove(self, run_id: UUID) -> bool:
        async with self._index_lock:
            if run_id not in self._runs:
                return False
            del self._runs[run_id]
            del self._locks[run_id]
            return True

    async def cleanup_expired(self) -> list[UUID]:
        now = self._now()
        expired: list[UUID] = []
        async with self._index_lock:
            for run_id, run in self._runs.items():
                if (
                    run.status in TERMINAL_RUN_STATUSES
                    and now - run.updated_at >= self.ttl
                ):
                    expired.append(run_id)
            for run_id in expired:
                del self._runs[run_id]
                del self._locks[run_id]
        return expired

    async def count(self) -> int:
        async with self._index_lock:
            return len(self._runs)

    async def active_count(self) -> int:
        async with self._index_lock:
            return sum(
                run.status not in TERMINAL_RUN_STATUSES for run in self._runs.values()
            )

    async def run_ids(self) -> list[UUID]:
        async with self._index_lock:
            return list(self._runs)

    def initial_sequences(self) -> dict[UUID, int]:
        return {
            run_id: snapshot.latest_event_sequence
            for run_id, snapshot in self._runs.items()
        }

    async def list_runs(self, *, limit: int) -> list[RunSummary]:
        async with self._index_lock:
            snapshots = sorted(
                self._runs.values(),
                key=lambda snapshot: snapshot.updated_at,
                reverse=True,
            )[:limit]
            return [
                RunSummary(
                    run_id=snapshot.run_id,
                    user_idea=snapshot.user_idea,
                    status=snapshot.status,
                    current_iteration=snapshot.current_iteration,
                    max_iterations=snapshot.max_iterations,
                    latest_score=(
                        snapshot.latest_evaluation.overall_score
                        if snapshot.latest_evaluation is not None
                        else None
                    ),
                    best_version=snapshot.best_version,
                    best_score=snapshot.best_score,
                    created_at=snapshot.created_at,
                    updated_at=snapshot.updated_at,
                )
                for snapshot in snapshots
            ]

    async def close(self) -> None:
        return None


class SQLiteRunStore(InMemoryRunStore):
    """Run snapshots mirrored to a local SQLite database."""

    def __init__(
        self,
        *,
        database_path: str,
        max_runs: int,
        ttl_seconds: int,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(max_runs=max_runs, ttl_seconds=ttl_seconds, now=now)
        path = Path(database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = path
        self._connection = sqlite3.connect(path, timeout=5)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                snapshot_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_updated_at ON runs(updated_at DESC)"
        )
        self._connection.commit()
        self._load_snapshots()

    def _load_snapshots(self) -> None:
        interrupted: list[RunSnapshot] = []
        rows = self._connection.execute(
            "SELECT snapshot_json FROM runs ORDER BY updated_at DESC"
        ).fetchall()
        for (snapshot_json,) in rows:
            snapshot = RunSnapshot.model_validate_json(snapshot_json)
            if snapshot.status not in TERMINAL_RUN_STATUSES:
                snapshot.status = RunStatus.FAILED
                if snapshot.active_node is not None:
                    snapshot.node_statuses[snapshot.active_node] = NodeStatus.FAILED
                snapshot.error = RunError(
                    code="RUN_INTERRUPTED",
                    message="The backend restarted before the run completed.",
                    retryable=True,
                )
                snapshot.active_node = None
                snapshot.completed_at = utc_now()
                snapshot.updated_at = snapshot.completed_at
                interrupted.append(snapshot)
            self._runs[snapshot.run_id] = snapshot
            self._locks[snapshot.run_id] = asyncio.Lock()
        for snapshot in interrupted:
            self._persist(snapshot)
        self._enforce_retention_on_load()

    def _enforce_retention_on_load(self) -> None:
        """Trim a database that holds more runs than ``max_runs`` allows.

        ``_load_snapshots`` bypasses ``create()``, so without this a database at
        or over the cap would make every subsequent ``create()`` raise
        ``StoreCapacityError`` until the TTL expired -- 30 days by default.
        """
        overflow = len(self._runs) - self.max_runs
        if overflow <= 0:
            return
        evicted = self._evictable_run_ids(needed=overflow)
        if not evicted:
            return
        for run_id in evicted:
            del self._runs[run_id]
            del self._locks[run_id]
        self._delete_rows(evicted)

    def _persist(self, snapshot: RunSnapshot) -> None:
        self._connection.execute(
            """
            INSERT INTO runs (run_id, snapshot_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                snapshot_json = excluded.snapshot_json,
                updated_at = excluded.updated_at
            """,
            (
                str(snapshot.run_id),
                snapshot.model_dump_json(),
                snapshot.updated_at.isoformat(),
            ),
        )
        self._connection.commit()

    def _delete_rows(self, run_ids: list[UUID]) -> None:
        if not run_ids:
            return
        self._connection.executemany(
            "DELETE FROM runs WHERE run_id = ?",
            [(str(run_id),) for run_id in run_ids],
        )
        self._connection.commit()

    async def make_room(self, *, incoming: int = 1) -> list[UUID]:
        evicted = await super().make_room(incoming=incoming)
        self._delete_rows(evicted)
        return evicted

    async def create(self, snapshot: RunSnapshot) -> None:
        await super().create(snapshot)
        try:
            self._persist(self.get_unlocked(snapshot.run_id))
        except Exception:
            await super().remove(snapshot.run_id)
            raise

    async def save_unlocked(self, run_id: UUID) -> None:
        self._persist(self.get_unlocked(run_id))

    async def remove(self, run_id: UUID) -> bool:
        removed = await super().remove(run_id)
        if removed:
            self._connection.execute(
                "DELETE FROM runs WHERE run_id = ?",
                (str(run_id),),
            )
            self._connection.commit()
        return removed

    async def cleanup_expired(self) -> list[UUID]:
        expired = await super().cleanup_expired()
        self._delete_rows(expired)
        return expired

    async def close(self) -> None:
        self._connection.close()
