from __future__ import annotations

from pathlib import Path

import openai
import pytest

from prd_benchmark.cases import Case, load_cases
from prd_benchmark.config import PilotConfig, load_config


@pytest.fixture(scope="session")
def config() -> PilotConfig:
    return load_config()


@pytest.fixture(scope="session")
def cases() -> dict[str, Case]:
    return {case.id: case for case in load_cases()}


@pytest.fixture(autouse=True)
def forbid_real_openai_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any attempt to build a real SDK client fails the test."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a real AsyncOpenAI client was constructed")

    monkeypatch.setattr(openai, "AsyncOpenAI", refuse)


@pytest.fixture
def output_root(tmp_path: Path) -> Path:
    return tmp_path / "out"
