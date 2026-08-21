from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pydantic.json_schema import models_json_schema
from sse_starlette.sse import EventSourceResponse

from backend.config import Settings, get_settings
from backend.errors import AppError, ProviderUnavailableError
from backend.event_store import EventStore, SQLiteEventStore
from backend.observability import log_event
from backend.providers.base import LLMProvider
from backend.providers.compatible import OpenAICompatibleLLMProvider
from backend.providers.mock import MockLLMProvider
from backend.providers.scenario import ScenarioController, ScenarioMockLLMProvider
from backend.run_manager import RunManager
from backend.run_store import InMemoryRunStore, SQLiteRunStore
from backend.schemas import (
    ControlResponse,
    CreateRunRequest,
    CreateRunResponse,
    ErrorDetail,
    ErrorResponse,
    EvaluationResult,
    HealthResponse,
    PRDVersion,
    ResumeRunRequest,
    RevisionPlan,
    RoleReview,
    RunEvent,
    RunListResponse,
    RunSnapshot,
    RunSummary,
)
from backend.workflow import AgentWorkflow

LOGGER = logging.getLogger("agentic_prd.api")


class E2EScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str


def error_response(
    *,
    code: str,
    message: str,
    request_id: str,
    status_code: int,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=request_id,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
    )


def request_id_for(request: Request) -> str:
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str):
        return existing
    return request.headers.get("x-request-id") or str(uuid4())


def create_app(
    *,
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    scenario_controller: ScenarioController | None = None
    if provider is None:
        if app_settings.enable_mock_llm:
            if app_settings.e2e_test_mode:
                scenario_controller = ScenarioController()
                provider = ScenarioMockLLMProvider(
                    controller=scenario_controller,
                    timeout_delay=app_settings.generator_timeout_seconds + 0.5,
                    delays_enabled=app_settings.mock_delays_enabled,
                    chunk_size=app_settings.mock_chunk_size,
                    generator_delay=app_settings.mock_generator_delay_seconds,
                    reviewer_delay=app_settings.mock_reviewer_delay_seconds,
                    optimizer_delay=app_settings.mock_optimizer_delay_seconds,
                    reviewer_stagger=0.4,
                )
            else:
                provider = MockLLMProvider(
                    delays_enabled=app_settings.mock_delays_enabled,
                    chunk_size=app_settings.mock_chunk_size,
                    generator_delay=app_settings.mock_generator_delay_seconds,
                    reviewer_delay=app_settings.mock_reviewer_delay_seconds,
                    optimizer_delay=app_settings.mock_optimizer_delay_seconds,
                )
        else:
            if app_settings.llm_provider == "deepseek":
                api_key = app_settings.deepseek_api_key
                base_url = app_settings.deepseek_base_url
                model = app_settings.deepseek_model
            else:
                api_key = app_settings.glm_api_key
                base_url = app_settings.glm_base_url
                model = app_settings.glm_model
            extra_body: dict[str, object] = {"thinking": {"type": "disabled"}}
            if api_key is None:
                raise ProviderUnavailableError
            provider = OpenAICompatibleLLMProvider(
                provider_name=app_settings.llm_provider,
                api_key=api_key.get_secret_value(),
                base_url=base_url,
                model=model,
                request_timeout_seconds=app_settings.llm_request_timeout_seconds,
                max_output_tokens=app_settings.llm_max_output_tokens,
                extra_body=extra_body,
            )
    if app_settings.database_path == ":memory:":
        run_store = InMemoryRunStore(
            max_runs=app_settings.max_retained_runs,
            ttl_seconds=app_settings.run_ttl_seconds,
        )
        event_store = EventStore(
            buffer_size=app_settings.event_buffer_size,
            heartbeat_seconds=app_settings.sse_heartbeat_seconds,
        )
    else:
        run_store = SQLiteRunStore(
            database_path=app_settings.database_path,
            max_runs=app_settings.max_retained_runs,
            ttl_seconds=app_settings.run_ttl_seconds,
        )
        event_store = SQLiteEventStore(
            database_path=app_settings.database_path,
            buffer_size=app_settings.event_buffer_size,
            heartbeat_seconds=app_settings.sse_heartbeat_seconds,
            initial_sequences=run_store.initial_sequences(),
        )
    manager = RunManager(
        settings=app_settings,
        provider=provider,
        run_store=run_store,
        event_store=event_store,
    )
    manager.set_workflow(AgentWorkflow(manager))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await manager.start()
        try:
            yield
        finally:
            await manager.shutdown()

    application = FastAPI(
        title="Agentic PRD Architect API",
        version="0.2.0",
        description="Agentic PRD generation, review, optimization, and SSE API.",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.manager = manager
    application.state.scenario_controller = scenario_controller
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.frontend_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "Last-Event-ID", "X-Request-ID"],
    )

    @application.middleware("http")
    async def request_observability(
        request: Request,
        call_next: Any,
    ) -> Any:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        started = monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        log_event(
            LOGGER,
            "http_request_completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((monotonic() - started) * 1000, 2),
        )
        return response

    @application.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(
            code=exc.code,
            message=exc.message,
            request_id=request_id_for(request),
            status_code=exc.status_code,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        _: RequestValidationError,
    ) -> JSONResponse:
        return error_response(
            code="REQUEST_VALIDATION_FAILED",
            message="The request did not match the API contract.",
            request_id=request_id_for(request),
            status_code=422,
        )

    @application.exception_handler(Exception)
    async def handle_unknown_error(request: Request, _: Exception) -> JSONResponse:
        return error_response(
            code="INTERNAL_ERROR",
            message="An unexpected internal error occurred.",
            request_id=request_id_for(request),
            status_code=500,
        )

    @application.get(
        "/api/health",
        response_model=HealthResponse,
        tags=["system"],
    )
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            mock_mode=app_settings.enable_mock_llm,
            provider="mock" if provider.is_mock else app_settings.llm_provider,
        )

    if scenario_controller is not None:

        @application.put("/api/test/scenario", tags=["test"])
        async def set_e2e_scenario(request: E2EScenarioRequest) -> dict[str, str]:
            try:
                selected = scenario_controller.set(request.scenario)
            except ValueError as exc:
                raise AppError(
                    "INVALID_E2E_SCENARIO",
                    "The requested E2E scenario is not supported.",
                    422,
                ) from exc
            return {"scenario": selected}

    @application.get(
        "/api/runs",
        response_model=RunListResponse,
        tags=["runs"],
    )
    async def list_runs(
        limit: int = Query(default=50, ge=1, le=100),
    ) -> RunListResponse:
        return RunListResponse(
            items=await manager.list_runs(limit=limit),
            total=await manager.run_store.count(),
        )

    @application.post(
        "/api/runs",
        response_model=CreateRunResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["runs"],
    )
    async def create_run(request: CreateRunRequest) -> CreateRunResponse:
        snapshot = await manager.create_run(request)
        return CreateRunResponse(
            run_id=snapshot.run_id,
            status=snapshot.status,
            events_url=f"/api/runs/{snapshot.run_id}/events",
            created_at=snapshot.created_at,
        )

    @application.get(
        "/api/runs/{run_id}",
        response_model=RunSnapshot,
        tags=["runs"],
    )
    async def get_run(run_id: UUID) -> RunSnapshot:
        return await manager.get_run(run_id)

    @application.post(
        "/api/runs/{run_id}/pause",
        response_model=ControlResponse,
        tags=["controls"],
    )
    async def pause_run(run_id: UUID) -> ControlResponse:
        snapshot = await manager.request_pause(run_id)
        return ControlResponse(
            run_id=run_id,
            status=snapshot.status,
            message="The run will pause at the next safe point.",
        )

    @application.post(
        "/api/runs/{run_id}/resume",
        response_model=ControlResponse,
        tags=["controls"],
    )
    async def resume_run(
        run_id: UUID,
        request: ResumeRunRequest,
    ) -> ControlResponse:
        snapshot = await manager.resume_run(run_id, request)
        return ControlResponse(
            run_id=run_id,
            status=snapshot.status,
            message="The run has resumed.",
        )

    @application.post(
        "/api/runs/{run_id}/cancel",
        response_model=ControlResponse,
        tags=["controls"],
    )
    async def cancel_run(run_id: UUID) -> ControlResponse:
        snapshot = await manager.cancel_run(run_id)
        return ControlResponse(
            run_id=run_id,
            status=snapshot.status,
            message="Cancellation has been requested.",
        )

    @application.get("/api/runs/{run_id}/events", tags=["events"])
    async def stream_events(
        run_id: UUID,
        after_sequence: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(
            default=None,
            alias="Last-Event-ID",
        ),
    ) -> EventSourceResponse:
        await manager.get_run(run_id)
        header_sequence = 0
        if last_event_id is not None:
            try:
                header_sequence = int(last_event_id)
            except ValueError as exc:
                raise AppError(
                    "INVALID_EVENT_ID",
                    "Last-Event-ID must be a non-negative integer.",
                    400,
                ) from exc
            if header_sequence < 0:
                raise AppError(
                    "INVALID_EVENT_ID",
                    "Last-Event-ID must be a non-negative integer.",
                    400,
                )
        cursor = max(after_sequence, header_sequence)
        event_store.replay(run_id, cursor)

        async def generate() -> AsyncIterator[dict[str, str]]:
            async for event in manager.stream_events(
                run_id,
                after_sequence=cursor,
            ):
                if event is None:
                    snapshot = await manager.get_run(run_id)
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps(
                            {"status": snapshot.status.value},
                            separators=(",", ":"),
                        ),
                    }
                    continue
                yield {
                    "id": str(event.sequence),
                    "event": event.event.value,
                    "data": event.model_dump_json(),
                }

        return EventSourceResponse(
            generate(),
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
            ping=3600,
        )

    contract_models = (
        CreateRunRequest,
        CreateRunResponse,
        ResumeRunRequest,
        ControlResponse,
        RoleReview,
        EvaluationResult,
        RevisionPlan,
        PRDVersion,
        RunSnapshot,
        RunSummary,
        RunListResponse,
        RunEvent,
        ErrorResponse,
    )

    def build_openapi_schema() -> dict[str, Any]:
        if application.openapi_schema is not None:
            return application.openapi_schema
        schema = get_openapi(
            title=application.title,
            version=application.version,
            description=application.description,
            routes=application.routes,
        )
        _, definitions = models_json_schema(
            [(model, "validation") for model in contract_models],
            ref_template="#/components/schemas/{model}",
        )
        schemas = definitions.get("$defs", {})
        schema.setdefault("components", {}).setdefault("schemas", {}).update(schemas)
        application.openapi_schema = schema
        return schema

    application.openapi = build_openapi_schema  # type: ignore[method-assign]
    return application


app = create_app()
