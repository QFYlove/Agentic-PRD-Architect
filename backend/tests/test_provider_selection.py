from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from backend.errors import AppError, RunConflictError
from backend.main import create_app
from backend.provider_catalog import (
    CatalogModel,
    CatalogProvider,
    ModelPricing,
    ProviderCatalog,
)
from backend.providers.mock import MockLLMProvider
from backend.schemas import CreateRunRequest, ReviewRole, TokenUsage
from backend.tests.helpers import make_manager, make_settings, make_sqlite_manager


def req(**extra: object) -> dict[str, object]:
    value: dict[str, object] = {"user_idea": "Build a podcast subscription product."}
    value.update(extra)
    return value


def catalog(
    provider: MockLLMProvider, *, pricing: ModelPricing | None = None
) -> ProviderCatalog:
    model = CatalogModel(
        "mock-prd-v1", "Historical Mock", "mock", provider, pricing or ModelPricing()
    )
    return ProviderCatalog((CatalogProvider("mock", "Mock Provider", (model,)),))


async def test_catalog_is_safe_and_explicit_selection_persists() -> None:
    app = create_app(
        settings=make_settings(), provider=MockLLMProvider(delays_enabled=False)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/providers")
        created = await client.post(
            "/api/runs", json=req(provider_id="mock", model_id="mock-prd-v1")
        )
        snapshot = await client.get(f"/api/runs/{created.json()['run_id']}")
    assert response.status_code == 200
    assert "providers" in response.json()
    assert set(response.json()["providers"][0]) == {
        "provider_id",
        "provider_display_name",
        "models",
    }
    assert (
        "api_key" not in response.text
        and "base_url" not in response.text
        and "pricing" not in response.text
    )
    assert snapshot.json()["provider_id"] == "mock"


@pytest.mark.parametrize(
    "payload", [{"provider_id": "mock"}, {"model_id": "mock-prd-v1"}]
)
async def test_partial_selection_rejected_without_persistence(
    payload: dict[str, str],
) -> None:
    app = create_app(
        settings=make_settings(), provider=MockLLMProvider(delays_enabled=False)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/api/runs", json=req(**payload))
    assert response.status_code == 422
    assert await app.state.manager.run_store.count() == 0


@pytest.mark.parametrize("provider,model", [("missing", "x"), ("mock", "missing")])
async def test_unknown_selection_rejected(provider: str, model: str) -> None:
    app = create_app(
        settings=make_settings(), provider=MockLLMProvider(delays_enabled=False)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/runs", json=req(provider_id=provider, model_id=model)
        )
    assert response.status_code == 422
    assert await app.state.manager.run_store.count() == 0


async def test_invalid_selection_does_not_trigger_retention_side_effect() -> None:
    manager = make_manager()
    called = False
    original = manager.run_store.make_room

    async def guarded_make_room(*, incoming: int = 1):
        nonlocal called
        called = True
        return await original(incoming=incoming)

    manager.run_store.make_room = guarded_make_room  # type: ignore[method-assign]
    with pytest.raises(AppError):
        await manager.create_run(
            CreateRunRequest(**req(provider_id="missing", model_id="x"))
        )
    assert called is False
    assert await manager.run_store.count() == 0


async def test_pricing_and_cleanup() -> None:
    manager = make_manager()
    await manager.start()
    run = await manager.create_run(CreateRunRequest(**req()))
    assert run.is_mock is True
    assert run.run_id in manager._run_bindings
    manager._release_run_resources(run.run_id)
    assert run.run_id not in manager._run_bindings
    await manager.shutdown()


async def test_selected_run_rehydrates(tmp_path: Path) -> None:
    path = str(tmp_path / "runs.sqlite")
    settings = make_settings(database_path=path)
    provider = MockLLMProvider(delays_enabled=False)
    first = make_sqlite_manager(
        database_path=path,
        settings=settings,
        provider=provider,
        catalog=catalog(provider),
    )
    await first.start()
    run = await first.create_run(
        CreateRunRequest(**req(provider_id="mock", model_id="mock-prd-v1"))
    )
    await first.shutdown()
    replacement = MockLLMProvider(delays_enabled=False)
    second = make_sqlite_manager(
        database_path=path,
        settings=settings,
        provider=replacement,
        catalog=catalog(replacement),
    )
    loaded = await second.get_run(run.run_id)
    assert loaded.provider_display_name == "Mock Provider"
    assert loaded.model_display_name == "Historical Mock"
    assert second.provider_for(run.run_id).is_mock
    await second.shutdown()


async def test_zero_pricing_is_valid() -> None:
    from backend.telemetry import estimate_cost

    assert (
        estimate_cost(
            TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30),
            pricing=ModelPricing(Decimal(0), Decimal(0)),
            is_mock=False,
        )
        == 0.0
    )


async def test_missing_and_model_specific_pricing() -> None:
    from backend.telemetry import estimate_cost

    usage = TokenUsage(
        input_tokens=1_000_000, output_tokens=1_000_000, total_tokens=2_000_000
    )
    assert estimate_cost(usage, pricing=ModelPricing(), is_mock=False) is None
    assert (
        estimate_cost(
            usage, pricing=ModelPricing(Decimal("1"), Decimal("2")), is_mock=False
        )
        == 3.0
    )
    assert (
        estimate_cost(
            usage, pricing=ModelPricing(Decimal("4"), Decimal("5")), is_mock=False
        )
        == 9.0
    )


async def test_run_manager_uses_selected_model_pricing() -> None:
    from backend.schemas import TokenUsage

    class MeteredMock(MockLLMProvider):
        is_mock = False

    a = MeteredMock(delays_enabled=False)
    b = MeteredMock(delays_enabled=False)
    selection = ProviderCatalog(
        (
            CatalogProvider(
                "a",
                "A",
                (
                    CatalogModel(
                        "m1", "M1", "a", a, ModelPricing(Decimal(1), Decimal(2))
                    ),
                ),
            ),
            CatalogProvider(
                "b",
                "B",
                (
                    CatalogModel(
                        "m2", "M2", "b", b, ModelPricing(Decimal(4), Decimal(5))
                    ),
                ),
            ),
        )
    )
    manager = make_manager(provider=a, catalog=selection)
    await manager.start()
    ra = await manager.create_run(
        CreateRunRequest(**req(provider_id="a", model_id="m1"))
    )
    rb = await manager.create_run(
        CreateRunRequest(**req(provider_id="b", model_id="m2"))
    )
    usage = TokenUsage(
        input_tokens=1_000_000, output_tokens=1_000_000, total_tokens=2_000_000
    )
    sa = await manager.record_usage(ra.run_id, node="x", usage=usage)
    sb = await manager.record_usage(rb.run_id, node="x", usage=usage)
    assert sa.estimated_cost_usd == 3.0 and sb.estimated_cost_usd == 9.0
    await manager.shutdown()


async def test_legacy_pricing_is_preserved_across_sqlite_restart(
    tmp_path: Path,
) -> None:
    class LegacyProvider(MockLLMProvider):
        is_mock = False

    path = str(tmp_path / "legacy-pricing.sqlite")
    settings = make_settings(
        database_path=path,
        model_input_price_per_million=Decimal("1"),
        model_output_price_per_million=Decimal("2"),
    )
    provider = LegacyProvider(delays_enabled=False)
    first = make_sqlite_manager(
        database_path=path, settings=settings, provider=provider
    )
    await first.start()
    run = await first.create_run(CreateRunRequest(**req()))
    usage = TokenUsage(
        input_tokens=1_000_000, output_tokens=1_000_000, total_tokens=2_000_000
    )
    before = await first.record_usage(run.run_id, node="pricing", usage=usage)
    assert before.estimated_cost_usd == 3.0
    assert before.cost_available is True
    await first.shutdown()

    second = make_sqlite_manager(
        database_path=path, settings=settings, provider=provider
    )
    loaded = await second.get_run(run.run_id)
    assert loaded.provider_id is None
    assert loaded.model_id is None
    after = await second.record_usage(run.run_id, node="pricing", usage=usage)
    assert after.estimated_cost_usd == 6.0
    assert after.cost_available is True
    await second.shutdown()


async def test_historical_unavailable_does_not_fallback(tmp_path: Path) -> None:
    path = str(tmp_path / "gone.sqlite")
    settings = make_settings(database_path=path)
    original = MockLLMProvider(delays_enabled=False)
    first = make_sqlite_manager(
        database_path=path,
        settings=settings,
        provider=original,
        catalog=catalog(original),
    )
    await first.start()
    run = await first.create_run(
        CreateRunRequest(**req(provider_id="mock", model_id="mock-prd-v1"))
    )
    await first.shutdown()
    fallback = MockLLMProvider(delays_enabled=False)
    empty = ProviderCatalog(
        (
            CatalogProvider(
                "other", "Other", (CatalogModel("m2", "M2", "other", fallback),)
            ),
        )
    )
    second = make_sqlite_manager(
        database_path=path, settings=settings, provider=fallback, catalog=empty
    )
    loaded = await second.get_run(run.run_id)
    assert (
        loaded.provider_id == "mock" and loaded.model_display_name == "Historical Mock"
    )
    with pytest.raises(RunConflictError) as exc:
        second.provider_for(run.run_id)
    assert exc.value.code == "PROVIDER_SELECTION_UNAVAILABLE"
    await second.shutdown()


class OverlapProvider(MockLLMProvider):
    def __init__(
        self, name: str, a_entered: asyncio.Event, b_entered: asyncio.Event
    ) -> None:
        super().__init__(delays_enabled=False)
        self.name = name
        self.a_entered, self.b_entered = a_entered, b_entered
        self.gated = False
        self.calls: list[str] = []

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = "English",
    ):
        self.calls.append(f"review:{role}")
        if not self.gated:
            self.gated = True
            own, other = (
                (self.a_entered, self.b_entered)
                if self.name == "A"
                else (self.b_entered, self.a_entered)
            )
            own.set()
            await other.wait()
        return await super().generate_review(
            role=role, prd=prd, iteration=iteration, output_language=output_language
        )


async def test_forced_overlap_keeps_run_bindings_isolated() -> None:
    a_entered, b_entered = asyncio.Event(), asyncio.Event()
    a, b = (
        OverlapProvider("A", a_entered, b_entered),
        OverlapProvider("B", a_entered, b_entered),
    )
    selection = ProviderCatalog(
        (
            CatalogProvider("a", "A", (CatalogModel("model-a", "A", "a", a),)),
            CatalogProvider("b", "B", (CatalogModel("model-b", "B", "b", b),)),
        )
    )
    manager = make_manager(
        provider=a, catalog=selection, settings=make_settings(max_concurrent_runs=2)
    )
    await manager.start()
    run_a = await manager.create_run(
        CreateRunRequest(**req(provider_id="a", model_id="model-a"))
    )
    run_b = await manager.create_run(
        CreateRunRequest(**req(provider_id="b", model_id="model-b"))
    )
    await asyncio.gather(
        manager.wait_for_completion(run_a.run_id, wait_seconds=5),
        manager.wait_for_completion(run_b.run_id, wait_seconds=5),
    )
    assert a_entered.is_set() and b_entered.is_set()
    assert len(a.calls) >= 3 and len(b.calls) >= 3
    assert manager.provider_for(run_a.run_id) is a
    assert manager.provider_for(run_b.run_id) is b
    await manager.shutdown()
