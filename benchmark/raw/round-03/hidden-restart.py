import asyncio
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path.cwd()))

from backend.run_store import SQLiteRunStore
from backend.schemas import RunSnapshot, RunStatus


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "hidden-restart.sqlite3")

        original = RunSnapshot(
            run_id=uuid4(),
            user_idea="Round 3 hidden restart acceptance",
            status=RunStatus.GENERATING,
        )

        first = SQLiteRunStore(
            database_path=db,
            max_runs=10,
            ttl_seconds=3600,
        )
        await first.create(original)
        await first.close()

        # First restart: active run must be normalized to persisted FAILED.
        second = SQLiteRunStore(
            database_path=db,
            max_runs=10,
            ttl_seconds=3600,
        )
        recovered_once = await second.get(original.run_id)

        assert recovered_once.status is RunStatus.FAILED
        assert recovered_once.error is not None
        assert recovered_once.error.code == "RUN_INTERRUPTED"
        assert recovered_once.completed_at is not None

        completed_at = recovered_once.completed_at
        updated_at = recovered_once.updated_at
        await second.close()

        # Second restart: must load the already-persisted terminal state,
        # not perform interruption recovery again.
        third = SQLiteRunStore(
            database_path=db,
            max_runs=10,
            ttl_seconds=3600,
        )
        recovered_twice = await third.get(original.run_id)

        assert recovered_twice.status is RunStatus.FAILED
        assert recovered_twice.error is not None
        assert recovered_twice.error.code == "RUN_INTERRUPTED"
        assert recovered_twice.completed_at == completed_at, (
            recovered_twice.completed_at,
            completed_at,
        )
        assert recovered_twice.updated_at == updated_at, (
            recovered_twice.updated_at,
            updated_at,
        )

        await third.close()

        print("PASS: restart recovery is persisted and stable across restarts")


asyncio.run(main())
