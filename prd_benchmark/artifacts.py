"""Write-once artifact storage: nothing the harness writes is ever overwritten."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from prd_benchmark.cases import PACKAGE_DIR

DEFAULT_OUTPUT_ROOT = PACKAGE_DIR
_BATCH_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
_SAFE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class ArtifactExistsError(FileExistsError):
    """Raised instead of overwriting an existing artifact."""


def validate_batch_id(batch_id: str) -> str:
    if not _BATCH_ID.fullmatch(batch_id):
        raise ValueError(
            "batch id must be 3-64 chars of lowercase letters, digits, '.', '_', '-'"
        )
    return batch_id


def _safe(part: str) -> str:
    if not _SAFE_PART.fullmatch(part):
        raise ValueError(f"unsafe path component: {part!r}")
    return part


class BatchLayout:
    """Paths for one batch under an output root."""

    def __init__(self, root: Path, batch_id: str) -> None:
        self.root = root
        self.batch_id = validate_batch_id(batch_id)

    @property
    def runs(self) -> Path:
        return self.root / "runs" / self.batch_id

    @property
    def scores(self) -> Path:
        return self.root / "scores" / self.batch_id

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    def run_dir(self, case_id: str, condition: str) -> Path:
        return self.runs / _safe(case_id) / _safe(condition)

    def judge_file(self, doc_id: str, judge_pass: int) -> Path:
        return self.scores / "judge" / f"{_safe(doc_id)}.pass{judge_pass}.json"

    def judge_raw_file(self, doc_id: str, judge_pass: int) -> Path:
        """Raw judge reply and call metadata, kept apart from the parsed file."""
        return self.scores / "judge_raw" / f"{_safe(doc_id)}.pass{judge_pass}.json"

    @property
    def review(self) -> Path:
        """Human-review workspace (packages, submissions, adjudication)."""
        return self.root / "review" / self.batch_id

    def human_file(self, doc_id: str) -> Path:
        return self.scores / "human" / f"{_safe(doc_id)}.yaml"


def _open_new(path: Path) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return path.open("x", encoding="utf-8", newline="\n")
    except FileExistsError as error:
        raise ArtifactExistsError(f"refusing to overwrite {path}") from error


def write_text_once(path: Path, text: str) -> None:
    with _open_new(path) as handle:
        handle.write(text)


def write_json_once(path: Path, value: Any) -> None:
    write_text_once(
        path, json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
    )


def write_jsonl_once(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with _open_new(path) as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
