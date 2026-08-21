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


def test_streaming_attempt_defaults_to_one_for_older_snapshots() -> None:
    """Snapshots persisted before the field existed must still deserialize."""
    payload = load_contract("run_snapshot.json")
    del payload["current_prd_attempt"]

    assert RunSnapshot.model_validate(payload).current_prd_attempt == 1


def test_best_version_defaults_to_absent_for_older_snapshots() -> None:
    """The pointer was added in a later round; old rows must still load."""
    payload = load_contract("run_snapshot.json")

    snapshot = RunSnapshot.model_validate(payload)

    assert snapshot.best_version is None
    assert snapshot.best_score is None
    assert snapshot.output_language == "en"


def test_capped_terminal_fixture_carries_the_best_version() -> None:
    capped = next(
        value
        for value in load_contract("terminal_snapshots.json")
        if value["status"] == "MAX_ITERATIONS_REACHED"
    )

    snapshot = RunSnapshot.model_validate(capped)

    assert snapshot.best_version == 2
    assert snapshot.best_score == 81.7


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
