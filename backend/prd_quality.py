"""Deterministic structure and fact-labelling checks for a generated PRD.

These checks read the Markdown the way the frontend will render it -- headings
outside code fences, GFM tables, list items, paragraphs -- so a passing report
means the document will actually parse into sections, not only that it contains
the right words. They are advisory: a formatting problem is reported as a warning
and never fails a generation. Only a missing required section marks the document
as structurally incomplete, and that is stated to the reader, not hidden.

The figure checks exist because of run 9fa59292: v2 added 65 numbers, 64 with no
source anywhere in the run, including a fabricated "内部试点观测值". A model will
not reliably police itself on that, so the backend counts what it can count and
hands the result to the reviewers as evidence.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from backend.schemas import GenerationMode, PRDQualityReport, QualityIssue

#: Target size in non-whitespace characters. The upper bounds are where the
#: report starts warning, not a cut-off: nothing is ever truncated to fit.
BUDGETS: dict[GenerationMode, tuple[int, int]] = {
    GenerationMode.STANDARD: (12_000, 18_000),
    GenerationMode.COMPACT: (7_000, 11_000),
}

#: A paragraph longer than this is a wall of text in a PRD.
LONG_PARAGRAPH_CHARACTERS = 300

#: Required sections, each matched by any of its heading keywords.
REQUIRED_SECTIONS: dict[str, tuple[str, ...]] = {
    "产品概述 / Overview": (
        "概述",
        "背景",
        "定位",
        "overview",
        "background",
        "summary",
        "problem",
    ),
    "用户与场景 / Users & scenarios": (
        "用户",
        "场景",
        "画像",
        "user",
        "persona",
        "scenario",
        "audience",
    ),
    "功能需求 / Requirements": (
        "功能",
        "需求",
        "范围",
        "requirement",
        "feature",
        "scope",
        "functional",
    ),
    "假设与待确认 / Assumptions & open questions": (
        "假设",
        "待确认",
        "待验证",
        "开放问题",
        "assumption",
        "open question",
        "tbd",
    ),
}

#: Labels the generator is told to put on a figure that is not user-supplied.
FIGURE_LABELS = (
    "[用户输入]",
    "[已验证事实]",
    "[假设]",
    "[建议]",
    "[待确认]",
    "[user input]",
    "[verified]",
    "[assumption]",
    "[recommendation]",
    "[tbd]",
    "假设",
    "待确认",
    "待验证",
    "待测算",
    "待调研",
    "建议初值",
    "估算",
    "assumption",
    "tbd",
    "to be confirmed",
    "estimate",
)

#: Phrases that present a figure as observed data. Without a source the user
#: supplied, they are invented evidence.
FABRICATED_SOURCE_PATTERNS = (
    re.compile(r"内部试点"),
    re.compile(r"试点(观测|数据|结果)"),
    re.compile(r"(?i)internal pilot"),
    re.compile(r"(?i)pilot (data|observation|results?)"),
)

#: A number with a unit that carries a decision: money, share, rate, size, speed.
_FIGURE = re.compile(
    r"(?<![\w.])\d+(?:\.\d+)?(?:\s*[—\-–~～至到]\s*\d+(?:\.\d+)?)?\s*"
    r"(?:%|％|个百分点|元|美元|万|亿|\$|USD|RMB|GB|TB|Mbps|倍)"
)

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_SECTION_NUMBER = re.compile(r"^\s*((?:\d+\.)*\d+)[.、\s]")
_INLINE_ENUMERATION = re.compile(r"(?:[（(]?\d+[)）]|[①②③④⑤⑥⑦⑧⑨])")


@dataclass
class Heading:
    level: int
    text: str
    line: int


@dataclass
class _Scan:
    headings: list[Heading] = field(default_factory=list)
    paragraphs: list[tuple[int, str, str | None]] = field(default_factory=list)
    tables: int = 0
    list_items: int = 0
    section_has_content: dict[int, bool] = field(default_factory=dict)


def _characters(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _scan(content: str) -> _Scan:
    scan = _Scan()
    in_fence = False
    in_table = False
    paragraph: list[str] = []
    paragraph_line = 0
    current: str | None = None
    current_index: int | None = None

    def flush() -> None:
        nonlocal paragraph
        if paragraph:
            scan.paragraphs.append((paragraph_line, " ".join(paragraph), current))
            if current_index is not None:
                scan.section_has_content[current_index] = True
        paragraph = []

    for number, raw in enumerate(content.splitlines(), start=1):
        line = raw.rstrip()
        if line.lstrip().startswith(("```", "~~~")):
            flush()
            in_fence = not in_fence
            if current_index is not None:
                scan.section_has_content[current_index] = True
            continue
        if in_fence:
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            in_table = False
            scan.headings.append(
                Heading(len(heading.group(1)), heading.group(2).strip(), number)
            )
            current = heading.group(2).strip()
            current_index = len(scan.headings) - 1
            scan.section_has_content.setdefault(current_index, False)
            continue
        if not line.strip():
            flush()
            in_table = False
            continue
        if _TABLE_ROW.match(line) or (in_table and line.strip().startswith("|")):
            flush()
            if not in_table:
                scan.tables += 1
                in_table = True
            if current_index is not None:
                scan.section_has_content[current_index] = True
            continue
        if _TABLE_SEPARATOR.match(line):
            continue
        in_table = False
        if _LIST_ITEM.match(line):
            flush()
            scan.list_items += 1
            if current_index is not None:
                scan.section_has_content[current_index] = True
            continue
        if line.lstrip().startswith(">"):
            flush()
            if current_index is not None:
                scan.section_has_content[current_index] = True
            continue
        if not paragraph:
            paragraph_line = number
        paragraph.append(line.strip())
    flush()
    return scan


def _excerpt(text: str, limit: int = 120) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _is_labelled(line: str) -> bool:
    lowered = line.casefold()
    return any(label in lowered for label in FIGURE_LABELS)


def figures_in(text: str) -> list[str]:
    return [re.sub(r"\s+", "", match.group(0)) for match in _FIGURE.finditer(text)]


def check_prd(
    content: str,
    *,
    user_text: str = "",
    mode: GenerationMode = GenerationMode.STANDARD,
) -> PRDQualityReport:
    """Structure, size, and fact-labelling report for one Markdown PRD."""
    scan = _scan(content)
    issues: list[QualityIssue] = []
    characters = _characters(content)

    heading_text = " ".join(heading.text.casefold() for heading in scan.headings)
    missing = [
        name
        for name, keywords in REQUIRED_SECTIONS.items()
        if not any(keyword in heading_text for keyword in keywords)
    ]
    for name in missing:
        issues.append(
            QualityIssue(
                code="missing_section",
                severity="error",
                message=f"缺少必需章节：{name}",
            )
        )

    if not scan.headings:
        issues.append(
            QualityIssue(
                code="no_headings",
                severity="error",
                message="文档没有任何 Markdown 标题，无法按章节阅读和定位。",
            )
        )
    elif scan.headings[0].level != 1:
        issues.append(
            QualityIssue(
                code="no_title",
                severity="warning",
                message="文档第一个标题不是一级标题。",
                line=scan.headings[0].line,
            )
        )
    if sum(1 for heading in scan.headings if heading.level == 1) > 1:
        issues.append(
            QualityIssue(
                code="multiple_titles",
                severity="warning",
                message="文档有多个一级标题，章节层级会被打乱。",
            )
        )

    previous_level = 0
    for heading in scan.headings:
        if previous_level and heading.level > previous_level + 1:
            issues.append(
                QualityIssue(
                    code="heading_level_skip",
                    severity="warning",
                    message=(f"标题层级从 H{previous_level} 跳到 H{heading.level}。"),
                    section=heading.text[:200],
                    line=heading.line,
                )
            )
        previous_level = heading.level

    for index, heading in enumerate(scan.headings):
        if scan.section_has_content.get(index):
            continue
        following = scan.headings[index + 1] if index + 1 < len(scan.headings) else None
        if following is not None and following.level > heading.level:
            continue  # A parent heading whose content lives in its children.
        issues.append(
            QualityIssue(
                code="empty_section",
                severity="warning",
                message="章节没有内容。",
                section=heading.text[:200],
                line=heading.line,
            )
        )

    normalized = Counter(
        re.sub(r"\s+", "", heading.text.casefold()) for heading in scan.headings
    )
    for heading in scan.headings:
        key = re.sub(r"\s+", "", heading.text.casefold())
        if normalized[key] > 1:
            issues.append(
                QualityIssue(
                    code="duplicate_heading",
                    severity="warning",
                    message="同名章节出现了不止一次。",
                    section=heading.text[:200],
                    line=heading.line,
                )
            )
            normalized[key] = 0
    numbers = Counter(
        match.group(1)
        for heading in scan.headings
        if (match := _SECTION_NUMBER.match(heading.text))
    )
    for heading in scan.headings:
        match = _SECTION_NUMBER.match(heading.text)
        if match and numbers[match.group(1)] > 1:
            issues.append(
                QualityIssue(
                    code="duplicate_section_number",
                    severity="warning",
                    message=f"章节编号 {match.group(1)} 重复。",
                    section=heading.text[:200],
                    line=heading.line,
                )
            )
            numbers[match.group(1)] = 0

    long_paragraphs = [
        (line, text, section)
        for line, text, section in scan.paragraphs
        if _characters(text) > LONG_PARAGRAPH_CHARACTERS
    ]
    for line, text, section in long_paragraphs[:8]:
        issues.append(
            QualityIssue(
                code="long_paragraph",
                severity="warning",
                message=(
                    f"段落 {_characters(text)} 字，"
                    f"超过 {LONG_PARAGRAPH_CHARACTERS} 字，建议拆成列表或表格。"
                ),
                section=section[:200] if section else None,
                line=line,
                excerpt=_excerpt(text),
            )
        )
    for line, text, section in scan.paragraphs:
        if len(_INLINE_ENUMERATION.findall(text)) >= 3:
            issues.append(
                QualityIssue(
                    code="inline_list",
                    severity="info",
                    message="段落里写了编号枚举，渲染时不会成为列表。",
                    section=section[:200] if section else None,
                    line=line,
                    excerpt=_excerpt(text),
                )
            )

    user_figures = set(figures_in(user_text))
    unlabeled: list[tuple[int, str, str]] = []
    lines = content.splitlines()
    for number, text_line in enumerate(lines, start=1):
        if _is_labelled(text_line):
            continue
        for figure in figures_in(text_line):
            if figure not in user_figures:
                unlabeled.append((number, figure, text_line))
    for number, figure, text_line in unlabeled[:6]:
        issues.append(
            QualityIssue(
                code="unlabeled_figure",
                severity="warning",
                message=(
                    f"数值 {figure} 没有标注来源或假设"
                    "（用户输入 / 假设 / 建议 / 待确认）。"
                ),
                line=number,
                excerpt=_excerpt(text_line),
            )
        )
    lowered_user = user_text.casefold()
    for number, text_line in enumerate(lines, start=1):
        for pattern in FABRICATED_SOURCE_PATTERNS:
            match = pattern.search(text_line)
            if match and match.group(0).casefold() not in lowered_user:
                issues.append(
                    QualityIssue(
                        code="fabricated_source",
                        severity="error",
                        message=(
                            f"引用了用户没有提供的数据来源「{match.group(0)}」，"
                            "请改为假设或待确认。"
                        ),
                        line=number,
                        excerpt=_excerpt(text_line),
                    )
                )
                break

    low, high = BUDGETS[mode]
    if characters > int(high * 1.25):
        issues.append(
            QualityIssue(
                code="over_budget",
                severity="warning",
                message=(
                    f"文档 {characters} 字，超过目标篇幅 {low}–{high} 字较多，"
                    "建议合并重复内容、压缩非 MVP 章节。"
                ),
            )
        )

    longest = max((_characters(text) for _, text, _ in scan.paragraphs), default=0)
    return PRDQualityReport(
        characters=characters,
        sections=len(scan.headings),
        tables=scan.tables,
        list_items=scan.list_items,
        paragraphs=len(scan.paragraphs),
        long_paragraphs=len(long_paragraphs),
        longest_paragraph=longest,
        unlabeled_figures=len(unlabeled),
        structure_complete=not missing and bool(scan.headings),
        missing_sections=missing,
        issues=issues,
        budget_characters=high,
    )


def outline(content: str) -> list[str]:
    """Every heading, indented by level, for an optimizer that cannot read it all."""
    return [
        f"{'  ' * (heading.level - 1)}{heading.text}"
        for heading in _scan(content).headings
    ]


def sections_matching(content: str, names: list[str]) -> str:
    """The full text of every section whose heading matches one of ``names``.

    A section runs until the next heading of the same or a higher level, so a
    matched H2 brings its H3 children with it.
    """
    from backend.scoring import section_key  # local: scoring imports schemas only

    lines = content.splitlines()
    headings = _scan(content).headings
    wanted = {section_key(name) for name in names if section_key(name)}
    wanted_text = {re.sub(r"\s+", "", name.casefold()) for name in names if name}
    chunks: list[str] = []
    for index, heading in enumerate(headings):
        key = section_key(heading.text)
        text_key = re.sub(r"\s+", "", heading.text.casefold())
        if key not in wanted and not any(
            candidate and (candidate in text_key or text_key in candidate)
            for candidate in wanted_text
        ):
            continue
        end = len(lines)
        for later in headings[index + 1 :]:
            if later.level <= heading.level:
                end = later.line - 1
                break
        chunks.append("\n".join(lines[heading.line - 1 : end]).strip())
    return "\n\n".join(dict.fromkeys(chunks))
