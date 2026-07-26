from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.schemas import (
    CreateRunRequest,
    EvaluationResult,
    NodeStatus,
    PRDRunState,
    PRDVersion,
    ReviewRole,
    RevisionItem,
    RevisionPlan,
    RevisionPriority,
    RevisionSource,
    RoleReview,
    RunStatus,
    TokenUsage,
)


def review(role: ReviewRole, score: int) -> RoleReview:
    return RoleReview(
        role=role,
        score=score,
        summary=f"{role} summary",
        feedback=[f"{role} feedback"],
    )


def test_create_request_normalizes_user_input() -> None:
    request = CreateRunRequest(user_idea="  A sufficiently detailed idea  ")

    assert request.user_idea == "A sufficiently detailed idea"
    assert request.max_iterations == 3


def test_create_request_rejects_whitespace_only_idea() -> None:
    with pytest.raises(ValidationError):
        CreateRunRequest(user_idea=" " * 12)


@pytest.mark.parametrize("length", [0, 9, 5001])
def test_create_request_rejects_idea_outside_length_bounds(length: int) -> None:
    with pytest.raises(ValidationError):
        CreateRunRequest(user_idea="x" * length)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quality_threshold", 49.9),
        ("quality_threshold", 100.1),
        ("max_iterations", 0),
        ("max_iterations", 6),
    ],
)
def test_create_request_rejects_numeric_boundaries(
    field: str,
    value: float | int,
) -> None:
    with pytest.raises(ValidationError):
        CreateRunRequest(
            user_idea="A sufficiently detailed idea",
            **{field: value},
        )


def test_create_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        CreateRunRequest(
            user_idea="A sufficiently detailed idea",
            unexpected=True,
        )


def test_all_run_and_node_statuses_round_trip() -> None:
    assert {RunStatus(status.value) for status in RunStatus} == set(RunStatus)
    assert {NodeStatus(status.value) for status in NodeStatus} == set(NodeStatus)


def test_evaluation_requires_server_average() -> None:
    result = EvaluationResult(
        tech=review(ReviewRole.TECH, 65),
        ux=review(ReviewRole.UX, 70),
        biz=review(ReviewRole.BIZ, 78),
        overall_score=71.0,
    )

    assert result.overall_score == 71.0


def test_evaluation_rejects_incorrect_average() -> None:
    with pytest.raises(ValidationError, match="server-computed average"):
        EvaluationResult(
            tech=review(ReviewRole.TECH, 65),
            ux=review(ReviewRole.UX, 70),
            biz=review(ReviewRole.BIZ, 78),
            overall_score=72.0,
        )


def test_evaluation_rejects_mismatched_role() -> None:
    with pytest.raises(ValidationError, match="matching role"):
        EvaluationResult(
            tech=review(ReviewRole.UX, 65),
            ux=review(ReviewRole.TECH, 70),
            biz=review(ReviewRole.BIZ, 78),
            overall_score=71.0,
        )


@pytest.mark.parametrize("score", [0, 100])
def test_review_accepts_score_boundaries_and_empty_feedback(score: int) -> None:
    result = RoleReview(role=ReviewRole.TECH, score=score, summary="Valid")

    assert result.score == score
    assert result.feedback == []


@pytest.mark.parametrize("score", [-1, 101])
def test_review_rejects_score_outside_boundaries(score: int) -> None:
    with pytest.raises(ValidationError):
        RoleReview(role=ReviewRole.TECH, score=score, summary="Invalid")


def test_evaluation_rounds_server_average_to_one_decimal() -> None:
    result = EvaluationResult(
        tech=review(ReviewRole.TECH, 66),
        ux=review(ReviewRole.UX, 67),
        biz=review(ReviewRole.BIZ, 67),
        overall_score=66.7,
    )

    assert result.overall_score == 66.7


def test_token_usage_requires_consistent_total() -> None:
    with pytest.raises(ValidationError, match="input \\+ output"):
        TokenUsage(input_tokens=10, output_tokens=5, total_tokens=20)


def test_collection_defaults_are_not_shared() -> None:
    first = RoleReview(role=ReviewRole.TECH, score=80, summary="First")
    second = RoleReview(role=ReviewRole.TECH, score=80, summary="Second")

    first.feedback.append("Only first")

    assert second.feedback == []


def test_nested_collection_defaults_are_not_shared() -> None:
    first = RevisionPlan(iteration=1, objective="First")
    second = RevisionPlan(iteration=1, objective="Second")

    first.items.append(
        RevisionItem(
            source_role=RevisionSource.USER,
            issue="Missing constraint",
            required_change="Add the constraint",
            target_section="Requirements",
            priority=RevisionPriority.HIGH,
        )
    )

    assert second.items == []


@pytest.mark.parametrize("version", [0, 6])
def test_prd_version_rejects_out_of_range_number(version: int) -> None:
    with pytest.raises(ValidationError):
        PRDVersion(
            version=version,
            content="# PRD",
            created_at=datetime.now(UTC),
        )


@pytest.mark.parametrize("source", list(RevisionSource))
@pytest.mark.parametrize("priority", list(RevisionPriority))
def test_revision_item_accepts_all_sources_and_priorities(
    source: RevisionSource,
    priority: RevisionPriority,
) -> None:
    item = RevisionItem(
        source_role=source,
        issue="Issue",
        required_change="Required change",
        target_section="Scope",
        priority=priority,
    )

    assert item.source_role is source
    assert item.priority is priority


def test_run_iteration_cannot_exceed_maximum() -> None:
    with pytest.raises(ValidationError, match="cannot exceed"):
        PRDRunState(
            run_id=UUID("0c98322f-51a5-47f0-8091-d8152df0e680"),
            user_idea="A sufficiently detailed idea",
            current_iteration=4,
            max_iterations=3,
            status=RunStatus.GENERATING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
