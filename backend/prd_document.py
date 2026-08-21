"""Completeness rules for a generated PRD.

A streamed document can end for reasons that have nothing to do with the model
being finished: an output cap, a safety filter, a resource rejection, or a
dropped connection. Every one of those yields text that *looks* like a PRD, so
without an explicit test the workflow commits a truncated document as a real
``PRDVersion`` and three reviewers then score half a document.

Two independent signals are checked here:

* ``finish_reason`` -- what the provider says about why it stopped.
* the completion marker -- what the model itself writes as its final line.

Either one failing rejects the attempt. The marker catches the case the reason
cannot: a provider that reports ``stop`` while the document is plainly unfinished.

The rejection is split three ways, because "incomplete" alone cannot be explained
to a user: an output cap means the document outgrew its budget, a missing marker
means the model quit early, and a resource rejection means the service itself
broke off. Each maps to a distinct error code and a distinct Chinese message.
"""

from __future__ import annotations

import re

from backend.errors import (
    ProviderContentFilteredError,
    ProviderOutputInterruptedError,
    ProviderOutputTruncatedError,
    ProviderOutputUnfinishedError,
)

PRD_COMPLETION_MARKER = "<!-- PRD_COMPLETE -->"

#: A clean stop. ``None`` is included because a provider is free to omit the
#: field entirely; the completion marker is what actually guards those.
COMPLETE_FINISH_REASONS = frozenset({"stop", "eos", ""})

#: The model ran out of room. The document outgrew the output budget, which is a
#: different problem from the service breaking off, and worth saying so.
TRUNCATED_FINISH_REASONS = frozenset({"length", "max_tokens"})

#: The provider refused to allocate the capacity to finish, or reported a reason
#: this backend does not recognise. Both are the provider breaking off mid-flight.
INTERRUPTED_FINISH_REASONS = frozenset({"insufficient_system_resource"})

#: The provider's own filter stopped the completion. Retrying the same prompt
#: reaches the same filter, so this is terminal.
FILTERED_FINISH_REASONS = frozenset({"content_filter"})

_MARKER = re.compile(r"[ \t]*<!--\s*PRD_COMPLETE\s*-->[ \t]*\n?")


def strip_completion_marker(content: str) -> str:
    """Remove every completion marker, wherever the model put it.

    The marker is a protocol between the backend and the model, so it must never
    reach a reader, a download, or a version diff. Occurrences are removed
    anywhere rather than only at the tail: a model that emits it once mid-document
    and once at the end would otherwise leave a stray comment in the PRD.
    """
    return _MARKER.sub("", content)


def has_completion_marker(content: str) -> bool:
    return _MARKER.search(content) is not None


def classify_finish_reason(finish_reason: str | None) -> str:
    """Bucket a raw provider reason into one of four verdicts.

    ``complete`` / ``truncated`` / ``interrupted`` / ``filtered``. An unrecognised
    reason counts as ``interrupted``: a provider that invents a new stop reason is
    far more likely to be reporting a problem than a clean finish, and the cost of
    being wrong is one extra attempt rather than a partial PRD.
    """
    if finish_reason is None:
        return "complete"
    normalized = finish_reason.strip().lower()
    if normalized in COMPLETE_FINISH_REASONS:
        return "complete"
    if normalized in FILTERED_FINISH_REASONS:
        return "filtered"
    if normalized in TRUNCATED_FINISH_REASONS:
        return "truncated"
    return "interrupted"


def validate_generated_prd(content: str, finish_reason: str | None) -> str:
    """Return the display-ready PRD, or raise if the attempt is not usable.

    Raises ``ProviderContentFilteredError`` (terminal) or one of the three
    ``ProviderIncompleteOutputError`` subclasses (retryable). Every one carries a
    fixed ``user_message``, so no provider-supplied text reaches the client.
    """
    verdict = classify_finish_reason(finish_reason)
    if verdict == "filtered":
        raise ProviderContentFilteredError("Provider filtered the completion")
    if verdict == "truncated":
        raise ProviderOutputTruncatedError("Provider hit its output limit")
    if verdict == "interrupted":
        raise ProviderOutputInterruptedError("Provider interrupted the generation")
    # A clean `stop` -- or no reason at all, which is what a stream that simply
    # ends looks like -- still has to prove the document finished.
    if not has_completion_marker(content):
        raise ProviderOutputUnfinishedError("Generated PRD is missing its end marker")
    stripped = strip_completion_marker(content).strip()
    if not stripped:
        raise ProviderOutputUnfinishedError("Generated PRD is empty")
    return stripped
