"""Pure, deterministic rules shared by the V3 services.

Nothing here touches storage or a model. Each function is the single place one
product rule is decided, so it can be tested on its own.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Collection, Iterable, Sequence

from backend.scoring import text_overlap
from backend.v3.models import ChangeClass, Severity

_SPACE = re.compile(r"\s+")
_MARKUP = re.compile(r"[\s`*_>#|\-:~\[\]()（）【】.,，。;；!！?？、\"'“”‘’]+")


def compact(text: str) -> str:
    """Whitespace-insensitive form used for substring evidence checks."""
    return _SPACE.sub("", text or "").casefold()


def semantic_form(text: str) -> str:
    """Text with Markdown markup, punctuation and whitespace removed."""
    return _MARKUP.sub("", text or "").casefold()


def quote_in(quote: str, sources: Iterable[str]) -> bool:
    """True when ``quote`` occurs, ignoring whitespace, in one of ``sources``."""
    needle = compact(quote)
    if len(needle) < 2:
        return False
    return any(needle in compact(source) for source in sources)


def strip_quotes(text: str) -> str:
    return text.strip().strip("\"'“”‘’「」『』").strip()


def evidence_found(evidence: str, bodies: Iterable[str]) -> bool:
    """A reviewer's evidence counts when its quoted part is in the document.

    Reviewers quote with 「」 or “”; when a quoted span exists only that span
    has to match, so "4.1 写道「…」" is checked on the quote itself.
    """
    spans = re.findall(r"[「“\"『](.+?)[」”\"』]", evidence)
    candidates = [strip_quotes(span) for span in spans] or [strip_quotes(evidence)]
    texts = list(bodies)
    return any(quote_in(candidate, texts) for candidate in candidates if candidate)


def same_problem(
    title_a: str,
    text_a: str,
    section_a: str | None,
    category_a: str,
    title_b: str,
    text_b: str,
    section_b: str | None,
    category_b: str,
) -> bool:
    """The V2 conservative match: same section and similar title, or same
    category and near-identical wording."""
    if section_a and section_b and section_a == section_b:
        if text_overlap(title_a, title_b) >= 0.5:
            return True
    if category_a and category_a == category_b and category_a != "other":
        return text_overlap(f"{title_a}{text_a}", f"{title_b}{text_b}") >= 0.75
    return text_overlap(f"{title_a}{text_a}", f"{title_b}{text_b}") >= 0.85


def similar_text(left: str, right: str, threshold: float = 0.8) -> bool:
    return text_overlap(left, right) >= threshold


def guard_severity(
    severity: Severity, category: str, confidence: float | None
) -> Severity:
    """A blocker the rubric does not allow becomes ``should_fix`` (V2 rule)."""
    if severity is not Severity.MUST_FIX:
        return severity
    if category == "quantification":
        return Severity.SHOULD_FIX
    if confidence is not None and confidence < 0.5:
        return Severity.SHOULD_FIX
    return severity


# --- Sections ----------------------------------------------------------------


def renumber(levels: Sequence[int]) -> list[str]:
    """Numbers for an ordered outline: chapters 1, 2…; subsections 2.1, 2.2…"""
    numbers: list[str] = []
    chapter = 0
    sub = 0
    for level in levels:
        if level <= 1 or chapter == 0:
            chapter += 1
            sub = 0
            numbers.append(str(chapter))
        else:
            sub += 1
            numbers.append(f"{chapter}.{sub}")
    return numbers


def summarize(body: str, limit: int = 220) -> str:
    """A short plain summary later sections read to stay consistent."""
    lines = []
    for raw in body.splitlines():
        line = re.sub(r"^[#>\-*\d.\s|]+", "", raw).strip()
        line = line.replace("|", " ").strip()
        if line:
            lines.append(line)
    text = "；".join(lines)
    return text if len(text) <= limit else text[: limit - 1] + "…"


_RULE_WORDS = (
    "必须",
    "不得",
    "不能",
    "不允许",
    "只能",
    "最多",
    "至少",
    "上限",
    "下限",
    "超过",
    "超时",
    "规则",
    "BR-",
    "限制",
    "额度",
    "过期",
    "权限",
    "must",
    "never",
    "at most",
    "at least",
    "limit",
)
_NUMBER = re.compile(r"\d")


def changed_lines(before: str, after: str) -> list[str]:
    diff = difflib.ndiff(before.splitlines(), after.splitlines())
    return [line[2:] for line in diff if line.startswith(("+ ", "- "))]


def classify_change(title: str, before: str, after: str) -> ChangeClass:
    """How much a section edit can change what the document says.

    Formatting-only edits (markup, punctuation, whitespace) change nothing a
    reviewer judged, so they never mark findings stale or trigger checks.
    """
    if semantic_form(before) == semantic_form(after):
        return ChangeClass.FORMAT
    lowered = title.casefold()
    if any(word in lowered for word in ("定位", "概述", "positioning", "overview")):
        return ChangeClass.POSITIONING
    if any(word in lowered for word in ("约束", "constraint")):
        return ChangeClass.CONSTRAINT
    joined = "\n".join(changed_lines(before, after))
    if any(word.casefold() in joined.casefold() for word in _RULE_WORDS):
        return ChangeClass.RULE
    if _NUMBER.search(joined) and any(
        word in lowered for word in ("规则", "rule", "异常", "验收")
    ):
        return ChangeClass.RULE
    if any(word in lowered for word in ("功能", "feature", "需求", "流程", "范围")):
        return ChangeClass.FEATURE
    return ChangeClass.DESCRIPTION


#: Classes whose change can invalidate other sections that rely on this one.
PROPAGATING = frozenset(
    {
        ChangeClass.FEATURE,
        ChangeClass.RULE,
        ChangeClass.POSITIONING,
        ChangeClass.CONSTRAINT,
    }
)


def line_diff(before: str, after: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line in difflib.ndiff(before.splitlines(), after.splitlines()):
        tag, text = line[:2], line[2:]
        if tag == "  ":
            out.append({"kind": "same", "text": text})
        elif tag == "- ":
            out.append({"kind": "del", "text": text})
        elif tag == "+ ":
            out.append({"kind": "add", "text": text})
    return out


# --- Export ------------------------------------------------------------------

_ANCHOR = re.compile(r"\[\[[A-Z]+-\d+\|([^\]]+)\]\]")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
#: A parenthesised or bracketed list of codes: "（POS-01、USR-02）", "[FR-03]".
_REF_GROUP = re.compile(
    r"\s*[（(\[]\s*(?:来源[:：]\s*)?"
    r"([A-Z]+-\d+(?:\s*[、,，/]\s*[A-Z]+-\d+)*)\s*[)）\]]"
)
_CODE = re.compile(r"\b[A-Z]+-\d+\b")


def codes_in(text: str) -> set[str]:
    return set(_CODE.findall(text or ""))


def strip_internal_refs(text: str, codes: Collection[str]) -> str:
    """Remove references to the project's own internal codes from prose.

    Only a reference made entirely of ``codes`` is removed, so "（型号 X-200）"
    or a code the user typed themselves (the caller leaves those out of
    ``codes``) is kept exactly as written.
    """
    if not codes or not text:
        return text

    def replace(match: re.Match[str]) -> str:
        parts = re.split(r"\s*[、,，/]\s*", match.group(1))
        return "" if all(part in codes for part in parts) else match.group(0)

    return _REF_GROUP.sub(replace, text)


def clean_for_export(body: str, codes: Collection[str] = ()) -> str:
    text = _ANCHOR.sub(r"\1", body)
    text = _COMMENT.sub("", text)
    text = strip_internal_refs(text, codes)
    return text.strip()


def markdown_document(
    title: str,
    sections: Sequence[tuple[int, str, str, str]],
    codes: Collection[str] = (),
) -> str:
    """``sections`` are (level, num, title, body)."""
    out = [f"# {strip_internal_refs(title, codes)}", ""]
    for level, num, heading, body in sections:
        heading = strip_internal_refs(heading, codes)
        out.append(f"{'##' if level <= 1 else '###'} {num} {heading}".rstrip())
        out.append("")
        cleaned = clean_for_export(body, codes)
        if cleaned:
            out.append(cleaned)
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def split_markdown(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Cut a pasted PRD into (level, title, body) by its ## / ### headings."""
    title = ""
    sections: list[tuple[int, str, list[str]]] = []
    preface: list[str] = []
    for raw in text.splitlines():
        match = re.match(r"^(#{1,3})\s+(.+?)\s*#*\s*$", raw)
        if match:
            depth = len(match.group(1))
            heading = match.group(2).strip()
            if depth == 1 and not title and not sections:
                title = heading
                continue
            heading = re.sub(r"^\d+(?:\.\d+)*[.、\s]+", "", heading).strip() or heading
            sections.append((1 if depth <= 2 else 2, heading, []))
            continue
        if sections:
            sections[-1][2].append(raw)
        else:
            preface.append(raw)
    result = [
        (level, heading, "\n".join(body).strip()) for level, heading, body in sections
    ]
    intro = "\n".join(preface).strip()
    if intro:
        result.insert(0, (1, "概述", intro))
    if not result:
        result = [(1, "正文", text.strip())]
    return title, result
