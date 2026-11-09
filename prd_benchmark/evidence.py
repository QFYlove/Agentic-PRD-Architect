"""Verbatim evidence checks for judge quotations."""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_QUOTE_CHARACTERS = 4
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Collapse whitespace only; every other character must match exactly.

    Judges re-flow line breaks and indentation when quoting, so whitespace runs
    compare equal. Punctuation, Markdown markup, and wording do not: a quote
    that paraphrases the document is not evidence.
    """
    return _WHITESPACE.sub(" ", text).strip()


@dataclass(frozen=True)
class QuoteCheck:
    quote: str
    valid: bool
    reason: str | None = None


class EvidenceIndex:
    def __init__(self, document: str) -> None:
        self._normalized = normalize(document)

    def check(self, quote: str) -> QuoteCheck:
        normalized = normalize(quote)
        if len(_WHITESPACE.sub("", normalized)) < MIN_QUOTE_CHARACTERS:
            return QuoteCheck(quote, False, "too_short")
        if normalized not in self._normalized:
            return QuoteCheck(quote, False, "not_found")
        return QuoteCheck(quote, True)

    def any_valid(self, quotes: list[str] | tuple[str, ...]) -> bool:
        return any(self.check(quote).valid for quote in quotes)


_IMPACT_QUOTE = re.compile(r"「([^」]+)」")
_PUNCTUATION = re.compile(r"[\s，。、；：,.;:!?！？（）()\"'“”]+")
MIN_IMPACT_EXPLANATION = 8
#: Explanations that name no behaviour at all. Matched after removing quotes
#: and punctuation, so padding them with a citation does not help.
GENERIC_IMPACTS = frozenset(
    {
        "与题面不一致",
        "与题面不符",
        "与要求不一致",
        "不符合要求",
        "措辞不同",
        "表述不同",
        "写法不同",
        "存在差异",
        "存在矛盾",
        "影响实现",
        "影响业务",
    }
)


def impact_problems(impact: str | None, index: EvidenceIndex) -> list[str]:
    """Why a ``behavior_impact`` does not ground a concrete behavioural claim.

    The impact must cite the document text that causes the different behaviour
    in 「」 (found verbatim by ``index``) and must explain the difference in its
    own words. A citation the document does not contain is a fabricated
    impact; a bare "inconsistent with the input" is a generic one.
    """
    if not impact or not impact.strip():
        return ["impact_missing"]
    quotes = _IMPACT_QUOTE.findall(impact)
    problems: list[str] = []
    if not quotes:
        problems.append("impact_without_document_quote")
    elif not index.any_valid(quotes):
        problems.append("impact_quote_not_found")
    explanation = _PUNCTUATION.sub("", _IMPACT_QUOTE.sub("", impact))
    if len(explanation) < MIN_IMPACT_EXPLANATION or explanation in GENERIC_IMPACTS:
        problems.append("impact_too_generic")
    return problems
