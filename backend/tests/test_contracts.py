import json
from pathlib import Path
from typing import Any

from backend.main import app
from backend.schemas import (
    CreateRunRequest,
    ErrorResponse,
    RunEvent,
    RunEventType,
    RunSnapshot,
    RunStatus,
)

CONTRACT_ROOT = Path(__file__).parents[2] / "contracts" / "v1"


def load_contract(name: str) -> Any:
    return json.loads((CONTRACT_ROOT / name).read_text(encoding="utf-8"))


def test_versioned_contract_examples_match_pydantic_models() -> None:
    CreateRunRequest.model_validate(load_contract("create_run_request.json"))
    RunSnapshot.model_validate(load_contract("run_snapshot.json"))
    RunEvent.model_validate(load_contract("run_event.json"))
    ErrorResponse.model_validate(load_contract("error_response.json"))


def test_contracts_cover_every_terminal_status_and_event_type() -> None:
    snapshots = [
        RunSnapshot.model_validate(value)
        for value in load_contract("terminal_snapshots.json")
    ]
    events = [
        RunEvent.model_validate(value) for value in load_contract("run_events.json")
    ]

    assert {snapshot.status for snapshot in snapshots} == {
        RunStatus.COMPLETED,
        RunStatus.MAX_ITERATIONS_REACHED,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    }
    assert {event.event for event in events} == set(RunEventType)


def test_openapi_contains_contract_models() -> None:
    schemas = app.openapi()["components"]["schemas"]

    for model_name in (
        "CreateRunRequest",
        "ResumeRunRequest",
        "RoleReview",
        "EvaluationResult",
        "RevisionPlan",
        "PRDVersion",
        "RunSnapshot",
        "RunEvent",
        "ErrorResponse",
    ):
        assert model_name in schemas
