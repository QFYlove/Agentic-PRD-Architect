from __future__ import annotations

import json
import logging
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
