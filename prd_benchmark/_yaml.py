from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


def load_yaml(path: Path) -> Any:
    """Parse one YAML file with the safe loader only."""
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def dump_yaml(value: Any) -> str:
    return str(yaml.safe_dump(value, allow_unicode=True, sort_keys=False))
