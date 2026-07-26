from __future__ import annotations

import json
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient

from backend.main import create_app
from backend.providers.mock import MockLLMProvider
from backend.schemas import RunStatus
from backend.tests.helpers import make_settings
from backend.tests.test_workflow import wait_for_status


def valid_request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "user_idea": "Build a podcast micro-subscription product.",
        "quality_threshold": 85,
        "max_iterations": 3,
    }
    payload.update(overrides)
    return payload


async def client_for(app: object) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app),  # type: ignore[arg-type]
        base_url="http://test",
    )


async def test_create_snapshot_health_and_openapi_contract() -> None:
    app = create_app(
        settings=make_settings(),
        provider=MockLLMProvider(delays_enabled=False),
    )
    async with await client_for(app) as client:
        health = await client.get("/api/health")
        created = await client.post("/api/runs", json=valid_request())
        run_id = created.json()["run_id"]
        result = await app.state.manager.wait_for_completion(
            UUID(run_id),
            wait_seconds=5,
        )
        snapshot = await client.get(f"/api/runs/{run_id}")
        openapi = await client.get("/openapi.json")

    assert health.json() == {
        "status": "ok",
        "mock_mode": True,
        "provider": "mock",
    }
    assert created.status_code == 202
    assert created.json()["events_url"].endswith("/events")
    assert result.status is RunStatus.COMPLETED
    assert snapshot.json()["latest_event_sequence"] > 0
    assert "RunSnapshot" in openapi.json()["components"]["schemas"]


async def test_validation_not_found_and_control_conflict_errors_are_uniform() -> None:
    app = create_app(
        settings=make_settings(),
        provider=MockLLMProvider(delays_enabled=False),
    )
    async with await client_for(app) as client:
        invalid = await client.post("/api/runs", json={"user_idea": "short"})
        missing = await client.get(f"/api/runs/{uuid4()}")
        created = await client.post("/api/runs", json=valid_request())
        run_id = created.json()["run_id"]
        await app.state.manager.wait_for_completion(UUID(run_id), wait_seconds=5)
        conflict = await client.post(f"/api/runs/{run_id}/pause")

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RUN_NOT_FOUND"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["request_id"]


async def test_concurrent_capacity_returns_429() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        chunk_size=10,
        generator_delay=0.05,
    )
    app = create_app(
        settings=make_settings(max_concurrent_runs=1),
        provider=provider,
    )
    async with await client_for(app) as client:
        first = await client.post("/api/runs", json=valid_request())
        second = await client.post("/api/runs", json=valid_request())
        await client.post(f"/api/runs/{first.json()['run_id']}/cancel")
        await app.state.manager.wait_for_completion(
            UUID(first.json()["run_id"]),
            wait_seconds=5,
        )

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RUN_CAPACITY_REACHED"


async def test_cors_allows_only_configured_frontend() -> None:
    app = create_app(
        settings=make_settings(),
        provider=MockLLMProvider(delays_enabled=False),
    )
    headers = {
        "Origin": "http://localhost:4321",
        "Access-Control-Request-Method": "POST",
    }
    async with await client_for(app) as client:
        allowed = await client.options("/api/runs", headers=headers)
        rejected = await client.options(
            "/api/runs",
            headers={**headers, "Origin": "https://attacker.example"},
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ("http://localhost:4321")
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


async def test_sse_replays_standard_business_events_and_closes_at_terminal() -> None:
    app = create_app(
        settings=make_settings(event_buffer_size=100),
        provider=MockLLMProvider(delays_enabled=False),
    )
    async with await client_for(app) as client:
        created = await client.post("/api/runs", json=valid_request())
        run_id = created.json()["run_id"]
        await app.state.manager.wait_for_completion(UUID(run_id), wait_seconds=5)
        response = await client.get(f"/api/runs/{run_id}/events?after_sequence=0")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert "event: run_started" in response.text
    assert "event: run_completed" in response.text
    ids = [
        int(line.removeprefix("id: "))
        for line in response.text.splitlines()
        if line.startswith("id: ")
    ]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    data_lines = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert all(json.loads(line)["sequence"] >= 1 for line in data_lines)


async def test_sse_reports_expired_and_invalid_resume_positions() -> None:
    app = create_app(
        settings=make_settings(event_buffer_size=10),
        provider=MockLLMProvider(delays_enabled=False),
    )
    async with await client_for(app) as client:
        created = await client.post("/api/runs", json=valid_request())
        run_id = created.json()["run_id"]
        await app.state.manager.wait_for_completion(UUID(run_id), wait_seconds=5)
        expired = await client.get(f"/api/runs/{run_id}/events?after_sequence=0")
        invalid = await client.get(
            f"/api/runs/{run_id}/events",
            headers={"Last-Event-ID": "invalid"},
        )

    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "EVENTS_EXPIRED"
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_EVENT_ID"


async def test_sse_uses_larger_of_query_and_last_event_id() -> None:
    app = create_app(
        settings=make_settings(event_buffer_size=100),
        provider=MockLLMProvider(delays_enabled=False),
    )
    async with await client_for(app) as client:
        created = await client.post("/api/runs", json=valid_request())
        run_id = created.json()["run_id"]
        result = await app.state.manager.wait_for_completion(
            UUID(run_id),
            wait_seconds=5,
        )
        response = await client.get(
            f"/api/runs/{run_id}/events?after_sequence=0",
            headers={"Last-Event-ID": str(result.latest_event_sequence - 1)},
        )

    ids = [
        int(line.removeprefix("id: "))
        for line in response.text.splitlines()
        if line.startswith("id: ")
    ]
    assert ids == [result.latest_event_sequence]


async def test_pause_resume_and_cancel_routes_delegate_to_manager() -> None:
    provider = MockLLMProvider(
        delays_enabled=True,
        generator_delay=0.001,
        reviewer_delay=0.03,
        optimizer_delay=0.001,
    )
    app = create_app(settings=make_settings(), provider=provider)
    async with await client_for(app) as client:
        created = await client.post("/api/runs", json=valid_request())
        run_id = UUID(created.json()["run_id"])
        await wait_for_status(app.state.manager, run_id, {RunStatus.REVIEWING})
        pause = await client.post(f"/api/runs/{run_id}/pause")
        await wait_for_status(app.state.manager, run_id, {RunStatus.PAUSED})
        resume = await client.post(
            f"/api/runs/{run_id}/resume",
            json={"user_override": "Add refund reconciliation."},
        )
        result = await app.state.manager.wait_for_completion(
            run_id,
            wait_seconds=5,
        )

        second = await client.post(
            "/api/runs",
            json=valid_request(user_idea="Build another cancellable product."),
        )
        second_id = UUID(second.json()["run_id"])
        cancel = await client.post(f"/api/runs/{second_id}/cancel")
        repeated = await client.post(f"/api/runs/{second_id}/cancel")
        cancelled = await app.state.manager.wait_for_completion(
            second_id,
            wait_seconds=5,
        )

    assert pause.json()["status"] == "PAUSE_REQUESTED"
    assert resume.json()["status"] == "OPTIMIZING"
    assert result.status is RunStatus.COMPLETED
    assert cancel.status_code == 200
    assert repeated.status_code == 200
    assert cancelled.status is RunStatus.CANCELLED


async def test_e2e_scenario_control_is_test_only_and_validated() -> None:
    production = create_app(
        settings=make_settings(app_env="production"),
        provider=MockLLMProvider(delays_enabled=False),
    )
    test_app = create_app(
        settings=make_settings(app_env="test", e2e_test_mode=True),
    )

    async with await client_for(production) as client:
        hidden = await client.put(
            "/api/test/scenario",
            json={"scenario": "malformed_structured"},
        )
    async with await client_for(test_app) as client:
        selected = await client.put(
            "/api/test/scenario",
            json={"scenario": "malformed_structured"},
        )
        invalid = await client.put(
            "/api/test/scenario",
            json={"scenario": "unknown"},
        )

    assert hidden.status_code == 404
    assert selected.json() == {"scenario": "malformed_structured"}
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_E2E_SCENARIO"
