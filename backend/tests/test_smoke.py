import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app
from backend.tests.helpers import make_settings


@pytest.mark.asyncio
async def test_health_endpoint() -> None:
    app = create_app(settings=make_settings())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mock_mode": True,
        "provider": "mock",
    }
