"""Programmatic document checks. Recorded as covariates; never scored."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from backend.prd_document import has_completion_marker

_HEADING = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S", re.MULTILINE)
_FENCE = re.compile(r"^```\s*([A-Za-z0-9_-]*)", re.MULTILINE)


@dataclass(frozen=True)
class DocumentChecks:
    characters: int
    non_whitespace_characters: int
    lines: int
    headings: int
    tables: int
    list_items: int
    mermaid_blocks: int
    code_fences_balanced: bool
    completion_marker_present: bool
    empty: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_document(text: str) -> DocumentChecks:
    lines = text.splitlines()
    tables = sum(1 for line in lines if _TABLE_SEPARATOR.match(line))
    fences = _FENCE.findall(text)
    # Every opening fence carries an info string or not; mermaid blocks are the
    # openings whose info string is "mermaid".
    mermaid = sum(1 for info in fences[0::2] if info.lower() == "mermaid")
    return DocumentChecks(
        characters=len(text),
        non_whitespace_characters=len(re.sub(r"\s", "", text)),
        lines=len(lines),
        headings=len(_HEADING.findall(text)),
        tables=tables,
        list_items=len(_LIST_ITEM.findall(text)),
        mermaid_blocks=mermaid,
        code_fences_balanced=len(fences) % 2 == 0,
        # The product strips the end marker before storing a version; one left
        # in a stored document would mean the stripping failed.
        completion_marker_present=has_completion_marker(text),
        empty=not text.strip(),
    )
