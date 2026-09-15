from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from backend.providers.base import LLMProvider


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: Decimal | None = None
    output_per_million: Decimal | None = None


@dataclass(frozen=True)
class CatalogModel:
    model_id: str
    model_display_name: str
    provider_id: str
    provider: LLMProvider
    pricing: ModelPricing = ModelPricing()
    available: bool = True


@dataclass(frozen=True)
class CatalogProvider:
    provider_id: str
    provider_display_name: str
    models: tuple[CatalogModel, ...]


@dataclass(frozen=True)
class ResolvedSelection:
    provider: CatalogProvider
    model: CatalogModel


@dataclass(frozen=True)
class RunExecution:
    provider: LLMProvider
    pricing: ModelPricing
    is_mock: bool


@dataclass(frozen=True)
class RunBinding:
    provider_id: str
    provider_display_name: str
    model_id: str
    model_display_name: str
    execution: RunExecution


class ProviderCatalog:
    def __init__(self, providers: tuple[CatalogProvider, ...]):
        self.providers = providers
        ids = [p.provider_id for p in providers]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate provider_id in catalog")
        for p in providers:
            mids = [m.model_id for m in p.models]
            if len(mids) != len(set(mids)):
                raise ValueError("Duplicate model_id within provider")
            if any(m.provider_id != p.provider_id for m in p.models):
                raise ValueError("Catalog model provider_id mismatch")
        self._providers: Mapping[str, CatalogProvider] = MappingProxyType(
            {p.provider_id: p for p in providers}
        )

    def resolve(self, provider_id: str, model_id: str) -> ResolvedSelection:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ValueError("Unknown provider")
        model = next((m for m in provider.models if m.model_id == model_id), None)
        if model is None:
            raise ValueError("Model is not available under this provider")
        if not model.available:
            raise ValueError("Selected provider/model is unavailable")
        return ResolvedSelection(provider, model)
