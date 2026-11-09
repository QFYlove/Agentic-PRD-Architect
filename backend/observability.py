from __future__ import annotations

import json
import logging
import re
import traceback
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


def _json_value(value: object) -> object:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit bounded JSON metadata; prompts, model output, and secrets are excluded."""

    payload: dict[str, object] = {"event": event}
    payload.update({key: _json_value(value) for key, value in fields.items()})
    logger.log(
        level,
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )


#: Credential shapes that can surface in a provider SDK's exception text: bearer
#: headers, ``sk-`` style keys, and ``key=value`` pairs whose name says secret.
_SECRET_PATTERNS = (
    re.compile(r"(?i)bearer\s+[a-z0-9._\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),
    re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|secret|password|authorization)"
        r"(\s*[=:]\s*)(['\"]?)[^\s'\",}]+"
    ),
)

#: Stack traces are for developers; this keeps one from flooding a log line.
MAX_STACK_CHARACTERS = 6000


def redact(text: str) -> str:
    """Mask anything shaped like a credential."""
    redacted = _SECRET_PATTERNS[0].sub("Bearer [REDACTED]", text)
    redacted = _SECRET_PATTERNS[1].sub("sk-[REDACTED]", redacted)
    return _SECRET_PATTERNS[2].sub(r"\1\2\3[REDACTED]", redacted)


def log_exception(
    logger: logging.Logger,
    event: str,
    error: BaseException,
    **fields: Any,
) -> None:
    """Record an exception's type and redacted stack as one structured line.

    Previously an unexpected exception became ``WORKFLOW_FAILED`` with nothing
    logged at all, so neither the user nor a developer could find the cause. The
    stack is kept -- it is the only way to locate an unknown failure -- but it is
    redacted and bounded, and it never reaches the client.
    """
    stack = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    log_event(
        logger,
        event,
        level=logging.ERROR,
        exception_type=type(error).__name__,
        exception_module=type(error).__module__,
        stack=redact(stack)[-MAX_STACK_CHARACTERS:],
        **fields,
    )
