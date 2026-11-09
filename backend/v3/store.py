"""SQLite storage for V3 projects.

One table per domain object, created by numbered migrations recorded in
``v3_schema_migrations``. The V2 ``runs`` and ``run_events`` tables are never
touched. Before the first V3 migration runs against an existing database file,
the whole file is copied to ``<dir>/backups/`` with SQLite's online backup API,
so the step can be undone by restoring that copy; ``rollback_v3`` drops only the
V3 tables for the same purpose without a restore.

All methods are synchronous and run on the event loop thread. A method that
writes several rows does so without awaiting in between, so no other coroutine
observes a half-applied change; ``transaction()`` makes the write atomic on disk.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from backend.v3.models import (
    Brief,
    Finding,
    FindingEvent,
    ItemRevision,
    Job,
    JobEvent,
    Link,
    Message,
    PRDSection,
    PRDVersion,
    Project,
    Proposal,
    ProposalChange,
    Question,
    RequirementItem,
    ReviewResult,
)

M = TypeVar("M", bound=BaseModel)

#: Ordered, append-only. Never edit a shipped migration; add a new one.
MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS v3_projects (
            id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            entry_mode TEXT NOT NULL, depth TEXT NOT NULL, language TEXT NOT NULL,
            round INTEGER NOT NULL, doc_title TEXT NOT NULL,
            outline_confirmed_at TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT
        );
        CREATE TABLE IF NOT EXISTS v3_counters (
            project_id TEXT NOT NULL, name TEXT NOT NULL, value INTEGER NOT NULL,
            PRIMARY KEY (project_id, name)
        );
        CREATE TABLE IF NOT EXISTS v3_messages (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, round INTEGER NOT NULL,
            role TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
            answers TEXT NOT NULL, changes TEXT NOT NULL,
            finding_codes TEXT NOT NULL, job_id TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_v3_messages ON v3_messages(project_id);
        CREATE TABLE IF NOT EXISTS v3_questions (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, code TEXT NOT NULL,
            round INTEGER NOT NULL, priority TEXT NOT NULL, text TEXT NOT NULL,
            purpose TEXT NOT NULL, target_group TEXT NOT NULL, finding_code TEXT,
            state TEXT NOT NULL, answer TEXT, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_v3_questions ON v3_questions(project_id);
        CREATE TABLE IF NOT EXISTS v3_items (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, code TEXT NOT NULL,
            "group" TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL,
            source_kind TEXT NOT NULL, source_round INTEGER NOT NULL,
            source_quote TEXT, priority TEXT NOT NULL, reason TEXT,
            links TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE (project_id, code)
        );
        CREATE TABLE IF NOT EXISTS v3_item_revisions (
            id TEXT PRIMARY KEY, item_id TEXT NOT NULL, before_content TEXT,
            after_content TEXT NOT NULL, before_status TEXT, after_status TEXT NOT NULL,
            actor TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_v3_revisions ON v3_item_revisions(item_id);
        CREATE TABLE IF NOT EXISTS v3_links (
            project_id TEXT NOT NULL, from_code TEXT NOT NULL, to_code TEXT NOT NULL,
            kind TEXT NOT NULL, origin TEXT NOT NULL,
            PRIMARY KEY (project_id, from_code, to_code, kind)
        );
        CREATE TABLE IF NOT EXISTS v3_briefs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, version INTEGER NOT NULL,
            sections TEXT NOT NULL, items TEXT NOT NULL,
            unconfirmed_count INTEGER NOT NULL, confirmed_at TEXT,
            created_at TEXT NOT NULL, UNIQUE (project_id, version)
        );
        CREATE TABLE IF NOT EXISTS v3_sections (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, code TEXT NOT NULL,
            position INTEGER NOT NULL, level INTEGER NOT NULL, num TEXT NOT NULL,
            title TEXT NOT NULL, goal TEXT NOT NULL, contents TEXT NOT NULL,
            item_codes TEXT NOT NULL, depends TEXT NOT NULL, open_points TEXT NOT NULL,
            body TEXT NOT NULL, origin TEXT NOT NULL, status TEXT NOT NULL,
            summary TEXT NOT NULL, needs_recheck INTEGER NOT NULL, error TEXT,
            row_version INTEGER NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE (project_id, code)
        );
        CREATE TABLE IF NOT EXISTS v3_versions (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, number INTEGER NOT NULL,
            label TEXT NOT NULL, source TEXT NOT NULL, actor TEXT NOT NULL,
            note TEXT NOT NULL, finding_codes TEXT NOT NULL,
            section_codes TEXT NOT NULL, sections TEXT NOT NULL,
            created_at TEXT NOT NULL, UNIQUE (project_id, number)
        );
        CREATE TABLE IF NOT EXISTS v3_findings (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, code TEXT NOT NULL,
            scope TEXT NOT NULL, reviewer TEXT NOT NULL, reviewers TEXT NOT NULL,
            kind TEXT NOT NULL, severity TEXT NOT NULL, title TEXT NOT NULL,
            category TEXT NOT NULL, section TEXT, evidence TEXT NOT NULL,
            evidence_verified INTEGER NOT NULL,
            problem TEXT NOT NULL, cause TEXT, impact TEXT NOT NULL,
            recommendation TEXT NOT NULL, confidence REAL, opportunity TEXT,
            related_items TEXT NOT NULL, related_sections TEXT NOT NULL,
            status TEXT NOT NULL, verification TEXT NOT NULL, user_note TEXT,
            first_seen_version INTEGER, last_checked_version INTEGER,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            UNIQUE (project_id, code)
        );
        CREATE TABLE IF NOT EXISTS v3_finding_events (
            id TEXT PRIMARY KEY, finding_id TEXT NOT NULL, from_status TEXT,
            to_status TEXT NOT NULL, actor TEXT NOT NULL, note TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_v3_finding_events
            ON v3_finding_events(finding_id);
        CREATE TABLE IF NOT EXISTS v3_reviews (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, job_id TEXT NOT NULL,
            reviewer TEXT NOT NULL, version_number INTEGER, summary TEXT NOT NULL,
            strengths TEXT NOT NULL, risks TEXT NOT NULL, blocking INTEGER NOT NULL,
            dimension_scores TEXT NOT NULL, score INTEGER,
            rubric_version TEXT NOT NULL, scoring_version TEXT NOT NULL,
            finding_codes TEXT NOT NULL, filtered_findings INTEGER NOT NULL,
            scope TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS v3_proposals (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, code TEXT NOT NULL,
            job_id TEXT NOT NULL, status TEXT NOT NULL, objective TEXT NOT NULL,
            declined TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS v3_proposal_changes (
            id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL,
            position INTEGER NOT NULL, change_type TEXT NOT NULL,
            section_code TEXT NOT NULL, new_title TEXT, reason TEXT NOT NULL,
            "before" TEXT NOT NULL, "after" TEXT NOT NULL, finding_codes TEXT NOT NULL,
            affected_sections TEXT NOT NULL, must_preserve TEXT NOT NULL,
            human_section INTEGER NOT NULL, base_row_version INTEGER NOT NULL,
            warnings TEXT NOT NULL, state TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS v3_jobs (
            id TEXT PRIMARY KEY, project_id TEXT NOT NULL, kind TEXT NOT NULL,
            status TEXT NOT NULL, input TEXT NOT NULL, result TEXT NOT NULL,
            error TEXT, provider TEXT, model TEXT, usage TEXT NOT NULL, cost REAL,
            trace_id TEXT NOT NULL, attempts INTEGER NOT NULL,
            created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
            latest_sequence INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_v3_jobs ON v3_jobs(project_id, created_at);
        CREATE TABLE IF NOT EXISTS v3_job_events (
            job_id TEXT NOT NULL, sequence INTEGER NOT NULL, event TEXT NOT NULL,
            payload TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY (job_id, sequence)
        );
        """,
    ),
    (
        2,
        """
        ALTER TABLE v3_findings ADD COLUMN brief_version INTEGER;
        """,
    ),
)

V3_TABLES: tuple[str, ...] = (
    "v3_projects",
    "v3_counters",
    "v3_messages",
    "v3_questions",
    "v3_items",
    "v3_item_revisions",
    "v3_links",
    "v3_briefs",
    "v3_sections",
    "v3_versions",
    "v3_findings",
    "v3_finding_events",
    "v3_reviews",
    "v3_proposals",
    "v3_proposal_changes",
    "v3_jobs",
    "v3_job_events",
)

#: model -> (table, primary key, JSON-encoded fields)
TABLES: dict[type[BaseModel], tuple[str, str, frozenset[str]]] = {
    Project: ("v3_projects", "id", frozenset()),
    Message: (
        "v3_messages",
        "id",
        frozenset({"answers", "changes", "finding_codes"}),
    ),
    Question: ("v3_questions", "id", frozenset()),
    RequirementItem: ("v3_items", "id", frozenset({"links"})),
    ItemRevision: ("v3_item_revisions", "id", frozenset()),
    Brief: ("v3_briefs", "id", frozenset({"sections", "items"})),
    PRDSection: (
        "v3_sections",
        "id",
        frozenset({"contents", "item_codes", "depends", "open_points"}),
    ),
    PRDVersion: (
        "v3_versions",
        "id",
        frozenset({"finding_codes", "section_codes", "sections"}),
    ),
    Finding: (
        "v3_findings",
        "id",
        frozenset({"reviewers", "opportunity", "related_items", "related_sections"}),
    ),
    FindingEvent: ("v3_finding_events", "id", frozenset()),
    ReviewResult: (
        "v3_reviews",
        "id",
        frozenset({"strengths", "risks", "dimension_scores", "finding_codes", "scope"}),
    ),
    Proposal: ("v3_proposals", "id", frozenset({"declined"})),
    ProposalChange: (
        "v3_proposal_changes",
        "id",
        frozenset({"finding_codes", "affected_sections", "must_preserve", "warnings"}),
    ),
    Job: ("v3_jobs", "id", frozenset({"input", "result", "error", "usage"})),
}


def new_id() -> str:
    return uuid4().hex


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    if hasattr(value, "value") and not isinstance(value, int | float | str):
        return value.value
    return value


def backup_database(path: Path, *, label: str = "pre-v3") -> Path | None:
    """Copy an existing database file before a schema change. ``None`` if new."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    target_dir = path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = target_dir / f"{path.stem}.{label}.{stamp}{path.suffix}"
    source = sqlite3.connect(path)
    try:
        destination = sqlite3.connect(target)
        try:
            source.backup(destination)
        finally:
            destination.close()
    finally:
        source.close()
    return target


def applied_migrations(connection: sqlite3.Connection) -> set[int]:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS v3_schema_migrations ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    return {
        int(row[0])
        for row in connection.execute("SELECT version FROM v3_schema_migrations")
    }


def migrate(connection: sqlite3.Connection, *, database_path: Path | None) -> list[int]:
    """Apply pending migrations. Safe to call on every start."""
    done = applied_migrations(connection)
    pending = [(number, sql) for number, sql in MIGRATIONS if number not in done]
    if not pending:
        return []
    if database_path is not None:
        backup_database(database_path)
    applied: list[int] = []
    for number, sql in pending:
        connection.executescript(f"BEGIN;\n{sql}\nCOMMIT;")
        connection.execute(
            "INSERT INTO v3_schema_migrations (version, applied_at) VALUES (?, ?)",
            (number, datetime.now(UTC).isoformat()),
        )
        connection.commit()
        applied.append(number)
    return applied


def rollback_v3(connection: sqlite3.Connection) -> None:
    """Drop every V3 table. V2 tables are left exactly as they were."""
    for table in (*V3_TABLES, "v3_schema_migrations"):
        connection.execute(f"DROP TABLE IF EXISTS {table}")
    connection.commit()


class ProjectStore:
    """Row-per-object persistence for every V3 model."""

    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        self._db: sqlite3.Connection | None = None
        self.applied: list[int] = []
        self._depth = 0
        self._column_cache: dict[str, frozenset[str]] = {}

    @property
    def _connection(self) -> sqlite3.Connection:
        """Opened (and migrated) on first use, not at import or app creation,
        so building the app never writes to a database nobody queried."""
        if self._db is None:
            memory = self.database_path == ":memory:"
            path = None if memory else Path(self.database_path)
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                ":memory:" if path is None else path, timeout=5
            )
            connection.row_factory = sqlite3.Row
            if path is not None:
                connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            self.applied = migrate(connection, database_path=path)
            self._db = connection
        return self._db

    def open(self) -> list[int]:
        """Open now and return the migrations this call applied."""
        _ = self._connection
        return self.applied

    # --- transactions -------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group writes into one commit. Nested calls join the outer one."""
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self._connection.rollback()
            raise
        self._depth -= 1
        if self._depth == 0:
            self._connection.commit()

    def _commit(self) -> None:
        if self._depth == 0:
            self._connection.commit()

    # --- generic rows -------------------------------------------------------

    @staticmethod
    def _meta(model_type: type[BaseModel]) -> tuple[str, str, frozenset[str]]:
        for cls in model_type.__mro__:
            if cls in TABLES:
                return TABLES[cls]
        raise KeyError(model_type)

    def _columns(self, table: str) -> frozenset[str]:
        cached = self._column_cache.get(table)
        if cached is None:
            cached = frozenset(
                str(row[1])
                for row in self._connection.execute(f"PRAGMA table_info({table})")
            )
            self._column_cache[table] = cached
        return cached

    def _row(self, model: BaseModel) -> dict[str, Any]:
        """Column values for a model; fields with no column (e.g. a proposal's
        loaded ``changes``) are stored in their own table and skipped here."""
        table, _, json_fields = self._meta(type(model))
        columns = self._columns(table)
        data = model.model_dump(mode="python")
        row: dict[str, Any] = {}
        for key, value in data.items():
            if key not in columns:
                continue
            if key in json_fields:
                row[key] = json.dumps(
                    model.model_dump(mode="json", include={key})[key],
                    ensure_ascii=False,
                )
            else:
                row[key] = _encode(value)
        return row

    def _decode(self, model_type: type[M], row: sqlite3.Row) -> M:
        _, _, json_fields = self._meta(model_type)
        data = dict(row)
        for key in json_fields:
            if key in data and data[key] is not None:
                data[key] = json.loads(data[key])
        allowed = set(model_type.model_fields)
        return model_type.model_validate(
            {key: value for key, value in data.items() if key in allowed}
        )

    def insert(self, model: BaseModel) -> None:
        table, _, _ = self._meta(type(model))
        row = self._row(model)
        columns = ", ".join(f'"{key}"' for key in row)
        marks = ", ".join("?" for _ in row)
        self._connection.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(row.values())
        )
        self._commit()

    def update(self, model: BaseModel) -> None:
        table, key, _ = self._meta(type(model))
        row = self._row(model)
        assignments = ", ".join(f'"{name}" = ?' for name in row if name != key)
        values = [value for name, value in row.items() if name != key]
        self._connection.execute(
            f'UPDATE {table} SET {assignments} WHERE "{key}" = ?',
            (*values, row[key]),
        )
        self._commit()

    def get(self, model_type: type[M], value: str) -> M | None:
        table, key, _ = self._meta(model_type)
        row = self._connection.execute(
            f'SELECT * FROM {table} WHERE "{key}" = ?', (value,)
        ).fetchone()
        return None if row is None else self._decode(model_type, row)

    def select(
        self,
        model_type: type[M],
        where: str = "1 = 1",
        params: Sequence[Any] = (),
        order: str | None = None,
    ) -> list[M]:
        table, _, _ = self._meta(model_type)
        sql = f"SELECT * FROM {table} WHERE {where}"
        if order:
            sql += f" ORDER BY {order}"
        rows = self._connection.execute(sql, tuple(params)).fetchall()
        return [self._decode(model_type, row) for row in rows]

    def delete(
        self, model_type: type[BaseModel], where: str, params: Sequence[Any]
    ) -> None:
        table, _, _ = self._meta(model_type)
        self._connection.execute(f"DELETE FROM {table} WHERE {where}", tuple(params))
        self._commit()

    def rows(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        return [tuple(row) for row in self._connection.execute(sql, tuple(params))]

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self._connection.execute(sql, tuple(params)).fetchone()
        return None if row is None else row[0]

    # --- codes ---------------------------------------------------------------

    def next_number(self, project_id: str, name: str) -> int:
        """Per-project monotonic counter for readable codes (USR-03, FD-07)."""
        self._connection.execute(
            "INSERT INTO v3_counters (project_id, name, value) VALUES (?, ?, 1) "
            "ON CONFLICT(project_id, name) DO UPDATE SET value = value + 1",
            (project_id, name),
        )
        value = self.scalar(
            "SELECT value FROM v3_counters WHERE project_id = ? AND name = ?",
            (project_id, name),
        )
        self._commit()
        return int(value)

    def next_code(self, project_id: str, prefix: str, width: int = 2) -> str:
        return f"{prefix}-{self.next_number(project_id, prefix):0{width}d}"

    # --- links ---------------------------------------------------------------

    def add_link(self, project_id: str, link: Link) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO v3_links "
            "(project_id, from_code, to_code, kind, origin) VALUES (?, ?, ?, ?, ?)",
            (project_id, link.from_code, link.to_code, link.kind, link.origin),
        )
        self._commit()

    def links(self, project_id: str) -> list[Link]:
        rows = self._connection.execute(
            "SELECT from_code, to_code, kind, origin FROM v3_links "
            "WHERE project_id = ? ORDER BY from_code, to_code",
            (project_id,),
        ).fetchall()
        return [Link.model_validate(dict(row)) for row in rows]

    def replace_links(
        self, project_id: str, from_code: str, kind: str, to_codes: Sequence[str]
    ) -> None:
        with self.transaction():
            self._connection.execute(
                "DELETE FROM v3_links WHERE project_id = ? AND from_code = ? "
                "AND kind = ?",
                (project_id, from_code, kind),
            )
            for code in dict.fromkeys(to_codes):
                self.add_link(
                    project_id,
                    Link(from_code=from_code, to_code=code, kind=kind, origin="rule"),
                )

    # --- job events ----------------------------------------------------------

    def append_job_event(self, event: JobEvent) -> None:
        self._connection.execute(
            "INSERT INTO v3_job_events (job_id, sequence, event, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                event.job_id,
                event.sequence,
                event.event,
                json.dumps(event.payload, ensure_ascii=False, default=str),
                event.created_at.isoformat(),
            ),
        )
        self._commit()

    def job_events(self, job_id: str, after_sequence: int = 0) -> list[JobEvent]:
        rows = self._connection.execute(
            "SELECT job_id, sequence, event, payload, created_at FROM v3_job_events "
            "WHERE job_id = ? AND sequence > ? ORDER BY sequence",
            (job_id, after_sequence),
        ).fetchall()
        return [
            JobEvent(
                job_id=row["job_id"],
                sequence=row["sequence"],
                event=row["event"],
                payload=json.loads(row["payload"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
