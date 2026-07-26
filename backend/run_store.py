from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from backend.errors import RunNotFoundError, StoreCapacityError
from backend.schemas import RunSnapshot
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

    def get_unlocked(self, run_id: UUID) -> RunSnapshot:
        try:
            return self._runs[run_id]
        except KeyError as exc:
            raise RunNotFoundError from exc

    async def get(self, run_id: UUID) -> RunSnapshot:
        lock = self.lock_for(run_id)
        async with lock:
            return self.get_unlocked(run_id).model_copy(deep=True)

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
