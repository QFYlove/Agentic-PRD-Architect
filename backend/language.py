"""Output-language detection and the directive that carries it to the model.

Every agent in the graph writes prose that a reader sees: the PRD itself, three
reviewer summaries, and a revision plan. Without an explicit instruction each of
those independently guesses a language from its own input, which is how one
reviewer ends up answering in English while the rest answer in Chinese.

The language is derived once per run from what the user actually wrote and then
passed to every provider call, so the whole run speaks with one voice.
"""

from __future__ import annotations

import re

#: Han characters, plus the extension and compatibility blocks a paste can carry.
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")

#: How many CJK characters make a request Chinese rather than English prose that
#: happens to quote a Chinese product name. ``user_idea`` has a 10-character
#: floor, so any genuinely Chinese idea clears this comfortably.
_CJK_THRESHOLD = 4

DEFAULT_OUTPUT_LANGUAGE = "en"

LANGUAGE_NAMES: dict[str, str] = {
    "zh": "Chinese (简体中文)",
    "en": "English",
}


def detect_output_language(*texts: str | None) -> str:
    """Pick the language the run should answer in from the user's own text."""
    joined = " ".join(text for text in texts if text)
    return "zh" if len(_CJK.findall(joined)) >= _CJK_THRESHOLD else "en"


def language_directive(output_language: str) -> str:
    """The system-message line that pins one language for one call.

    An unknown code falls back to English rather than raising: a stale snapshot
    or a future language code should not be able to fail a run.
    """
    name = LANGUAGE_NAMES.get(output_language, LANGUAGE_NAMES[DEFAULT_OUTPUT_LANGUAGE])
    return (
        f"OUTPUT LANGUAGE: write every word you emit in {name}. "
        "This covers headings, prose, list items, and every string field of a "
        "structured response -- summary, strengths, issue, recommendation, "
        "objective, required_change, and target_section included. Never mix "
        "another language into the same document or review. Leave code "
        "identifiers, metric names, and proper nouns in their original form. "
        "Enum values such as severity and priority stay in their exact English "
        "form."
    )
