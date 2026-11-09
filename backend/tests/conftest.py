"""Shared fixtures for the V3 API tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app
from backend.providers.mock import MockLLMProvider
from backend.tests.helpers import make_settings


@pytest.fixture
def app(tmp_path: Path) -> Any:
    """A full app on a temporary SQLite file with the mock model."""
    return create_app(
        settings=make_settings(database_path=str(tmp_path / "v3.sqlite3")),
        provider=MockLLMProvider(delays_enabled=False),
    )


@pytest.fixture
async def client(app: Any) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http
