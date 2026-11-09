"""Round 9 generation-reliability and iteration-semantics tests.

The defects these cover all came out of one real DeepSeek run: a truncated third
version was committed as a legal ``PRDVersion``, the run reported its lowest-
scoring final version as the result, and the reviewers were fed a half document.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.errors import (
    ProviderContentFilteredError,
    ProviderIncompleteOutputError,
    ProviderOutputTruncatedError,
    ProviderOutputUnfinishedError,
    RetryableProviderError,
)
from backend.language import (
    DEFAULT_OUTPUT_LANGUAGE,
    detect_output_language,
    language_directive,
)
from backend.prd_document import (
    PRD_COMPLETION_MARKER,
    classify_finish_reason,
    has_completion_marker,
    strip_completion_marker,
    validate_generated_prd,
)
from backend.providers.base import ProviderStructuredResult, ProviderTextEvent
from backend.providers.mock import MockLLMProvider
from backend.schemas import (
    CreateRunRequest,
    FeedbackSeverity,
    GenerationMode,
    RecoveryAction,
    ReviewRole,
    RevisionPlan,
    RunEventType,
    RunStatus,
    TokenUsage,
)
from backend.tests.helpers import finding, make_manager, make_settings, review_value


def test_marker_is_stripped_from_anywhere_and_detected() -> None:
    body = f"# PRD\n{PRD_COMPLETION_MARKER}\nMore text\n{PRD_COMPLETION_MARKER}\n"

    assert has_completion_marker(body)
    assert PRD_COMPLETION_MARKER not in strip_completion_marker(body)
    assert "More text" in strip_completion_marker(body)


@pytest.mark.parametrize(
    ("reason", "verdict"),
    [
        (None, "complete"),
        ("stop", "complete"),
        ("STOP", "complete"),
        ("", "complete"),
        ("length", "truncated"),
        ("max_tokens", "truncated"),
        ("insufficient_system_resource", "interrupted"),
        ("content_filter", "filtered"),
        # A reason nobody has seen before is the provider reporting a problem,
        # not a clean finish, so it buckets with the interruptions.
        ("some_new_vendor_reason", "interrupted"),
    ],
)
def test_finish_reasons_bucket_conservatively(reason: str | None, verdict: str) -> None:
    assert classify_finish_reason(reason) == verdict


def test_validation_accepts_a_marked_document_and_removes_the_marker() -> None:
    content = f"# PRD\n\n## Scope\nAll of it.\n{PRD_COMPLETION_MARKER}\n"

    validated = validate_generated_prd(content, "stop")

    assert validated.endswith("All of it.")
    assert PRD_COMPLETION_MARKER not in validated


@pytest.mark.parametrize(
    ("reason", "expected_code"),
    [
        ("insufficient_system_resource", "PROVIDER_OUTPUT_INTERRUPTED"),
        ("some_new_vendor_reason", "PROVIDER_OUTPUT_INTERRUPTED"),
    ],
)
def test_incomplete_causes_keep_distinct_codes(reason: str, expected_code: str) -> None:
    """Each cause needs its own code: the frontend words differ per cause.

    They used to share ``PROVIDER_OUTPUT_INCOMPLETE``, which made "your document
    is too long" and "the service broke off" read as the same sentence.
    """
    with pytest.raises(ProviderIncompleteOutputError) as excinfo:
        validate_generated_prd(f"# PRD\n{PRD_COMPLETION_MARKER}", reason)

    assert excinfo.value.retryable is True
    assert excinfo.value.code == expected_code
    # Nothing the provider said can reach the client.
    assert reason not in excinfo.value.user_message


@pytest.mark.parametrize("reason", ["length", "max_tokens"])
def test_an_output_cap_is_its_own_non_retryable_failure(reason: str) -> None:
    """Hitting the cap is not something the identical request can get past.

    It used to subclass the retryable incomplete-output error, which is how run
    9fa59292 sent the same 18,225-token request twice and lost 68,450 tokens.
    """
    with pytest.raises(ProviderOutputTruncatedError) as excinfo:
        validate_generated_prd(f"# PRD\n{PRD_COMPLETION_MARKER}", reason)

    assert not isinstance(excinfo.value, RetryableProviderError)
    assert excinfo.value.retryable is False
    assert excinfo.value.code == "PROVIDER_OUTPUT_TRUNCATED"
    assert reason not in excinfo.value.user_message


def test_content_filter_is_terminal_rather_than_retryable() -> None:
    with pytest.raises(ProviderContentFilteredError) as excinfo:
        validate_generated_prd(f"# PRD\n{PRD_COMPLETION_MARKER}", "content_filter")

    assert excinfo.value.retryable is False
    assert excinfo.value.code == "PROVIDER_CONTENT_FILTERED"


def test_a_clean_stop_without_the_marker_is_still_rejected() -> None:
    """A provider reporting ``stop`` on an unfinished document is the real case."""
    with pytest.raises(ProviderOutputUnfinishedError) as excinfo:
        validate_generated_prd("# PRD\n\n## Scope\nCut off mid-sen", "stop")

    assert excinfo.value.code == "PROVIDER_OUTPUT_UNFINISHED"


def test_a_stream_that_just_ends_is_unfinished_rather_than_truncated() -> None:
    """No ``finish_reason`` at all is what a stream that simply stops looks like."""
    with pytest.raises(ProviderOutputUnfinishedError):
        validate_generated_prd("# PRD\n\n## Scope\nCut off mid-sen", None)


def test_marker_alone_is_not_a_document() -> None:
    with pytest.raises(ProviderOutputUnfinishedError):
        validate_generated_prd(f"  \n{PRD_COMPLETION_MARKER}\n  ", "stop")


class TruncatingProvider(MockLLMProvider):
    """Every attempt of a chosen version stops at the output cap.

    Records each request it receives, so a test can prove the identical request
    was never sent twice.
    """

    def __init__(self, *, truncate_versions: set[int] | None = None) -> None:
        super().__init__(delays_enabled=False)
        self.truncate_versions = truncate_versions or {1}
        self.requests: list[tuple[int, str | None, GenerationMode]] = []
        self.reviews = 0

    async def stream_prd(
        self,
        *,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan: RevisionPlan | None,
        baseline_prd: str | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
        generation_mode: GenerationMode = GenerationMode.STANDARD,
    ) -> AsyncIterator[ProviderTextEvent]:
        self.requests.append((iteration, baseline_prd, generation_mode))
        if iteration in self.truncate_versions:
            yield ProviderTextEvent(
                delta="# Product Requirements Document\n\n## Scope\nCut off mid-sen",
                model="mock-prd-v1",
            )
            yield ProviderTextEvent(
                model="mock-prd-v1",
                finish_reason="length",
                usage=TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30),
            )
            return
        async for event in super().stream_prd(
            user_idea=user_idea,
            target_audience=target_audience,
            user_constraints=user_constraints,
            iteration=iteration,
            revision_plan=revision_plan,
            baseline_prd=baseline_prd,
            output_language=output_language,
            generation_mode=generation_mode,
        ):
            yield event

    async def generate_review(self, **kwargs) -> ProviderStructuredResult:  # type: ignore[no-untyped-def,override]
        self.reviews += 1
        return await super().generate_review(**kwargs)


async def test_truncation_is_never_retried_with_the_same_request() -> None:
    """Replaces the old "truncation retries exactly once" contract.

    One attempt, one failure, recorded as non-retryable with a recovery action,
    the partial text kept as an incomplete draft and never as a version.
    """
    provider = TruncatingProvider(truncate_versions={1})
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a permanently truncated product.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)
    events = manager.event_store.replay(created.run_id, 0)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "PROVIDER_OUTPUT_TRUNCATED"
    assert result.error.retryable is False
    assert result.error.node == "generator"
    assert result.error.stage == "generation"
    assert result.error.version == 1
    assert result.error.attempt == 1
    assert result.error.recovery_action is RecoveryAction.REGENERATE_COMPACT
    assert result.error.trace_id == result.trace_id
    assert len(provider.requests) == 1
    assert RunEventType.PRD_STREAM_RESET not in {event.event for event in events}
    assert result.versions == []
    assert provider.reviews == 0
    assert result.incomplete_draft is not None
    assert result.incomplete_draft.version == 1
    assert result.incomplete_draft.error_code == "PROVIDER_OUTPUT_TRUNCATED"
    # The tokens the failed attempt was billed for still count.
    assert result.total_tokens.output_tokens == 20


async def test_a_truncated_v2_keeps_v1_as_the_best_and_offers_continue() -> None:
    provider = TruncatingProvider(truncate_versions={2})
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product whose second version outgrows the cap.",
            quality_threshold=99,
            max_iterations=3,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.FAILED
    assert [version.version for version in result.versions] == [1]
    assert result.best_version == 1
    assert result.error is not None
    assert result.error.version == 2
    assert result.error.recovery_action is RecoveryAction.CONTINUE_FROM_BEST
    assert [request[0] for request in provider.requests] == [1, 2]
    assert result.incomplete_draft is not None
    assert result.incomplete_draft.version == 2
    failed = [t for t in result.node_timings if not t.succeeded]
    assert [(t.node, t.version, t.attempt) for t in failed] == [("generator", 2, 1)]


async def test_continue_from_best_starts_a_compact_run_and_keeps_the_source() -> None:
    provider = TruncatingProvider(truncate_versions={2})
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product recovered from its best version.",
            quality_threshold=99,
            max_iterations=3,
        )
    )
    source = await manager.wait_for_completion(created.run_id, wait_seconds=5)
    provider.truncate_versions = set()
    source_json = source.model_dump_json()

    from backend.schemas import RecoveryMode

    recovered = await manager.create_recovery_run(
        source.run_id, RecoveryMode.CONTINUE_FROM_BEST
    )
    result = await manager.wait_for_completion(recovered.run_id, wait_seconds=5)

    assert recovered.run_id != source.run_id
    assert result.source_run_id == source.run_id
    assert result.source_version == 1
    assert result.generation_mode is GenerationMode.COMPACT
    # The first generation of the new run edits the source's best document,
    # in compact mode, with the plan the source had built from it.
    first_request = provider.requests[2]
    assert first_request[1] == source.versions[0].content
    assert first_request[2] is GenerationMode.COMPACT
    assert result.versions[0].revision_plan is not None
    # The source run is not touched.
    assert (await manager.get_run(source.run_id)).model_dump_json() == source_json


async def test_a_running_run_cannot_be_recovered() -> None:
    from backend.errors import RunConflictError
    from backend.schemas import RecoveryMode

    manager = make_manager(
        provider=MockLLMProvider(delays_enabled=True, generator_delay=0.05)
    )
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product that is still running.")
    )

    with pytest.raises(RunConflictError):
        await manager.create_recovery_run(created.run_id, RecoveryMode.RESTART)
    await manager.cancel_run(created.run_id)


class MissingMarkerProvider(MockLLMProvider):
    """Reports a clean stop but never writes the end marker."""

    def __init__(self) -> None:
        super().__init__(delays_enabled=False)
        self.attempts = 0

    async def stream_prd(
        self,
        *,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan: RevisionPlan | None,
        baseline_prd: str | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> AsyncIterator[ProviderTextEvent]:
        del baseline_prd, output_language
        self.attempts += 1
        content = strip_completion_marker(
            self._prd(
                user_idea,
                target_audience,
                user_constraints,
                iteration,
                revision_plan,
            )
        )
        yield ProviderTextEvent(delta=content, model="mock-prd-v1")
        yield ProviderTextEvent(
            model="mock-prd-v1",
            finish_reason="stop",
            usage=TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30),
        )


async def test_a_document_missing_its_end_marker_fails_the_generation() -> None:
    provider = MissingMarkerProvider()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a marker-less product document.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "PROVIDER_OUTPUT_UNFINISHED"
    assert provider.attempts == 2


async def test_committed_versions_never_contain_the_protocol_marker() -> None:
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a marker-stripping product.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert result.versions
    for version in result.versions:
        assert PRD_COMPLETION_MARKER not in version.content
    assert PRD_COMPLETION_MARKER not in result.current_prd


class RegressingScoreProvider(MockLLMProvider):
    """v1 66.7, v2 81.7, v3 78.3 -- the real DeepSeek run's score curve."""

    CURVES: dict[ReviewRole, tuple[int, ...]] = {
        ReviewRole.TECH: (65, 80, 77),
        ReviewRole.UX: (66, 82, 78),
        ReviewRole.BIZ: (69, 83, 80),
    }

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> ProviderStructuredResult:
        del output_language
        curve = self.CURVES[role]
        score = curve[min(iteration, len(curve)) - 1]
        value = review_value(
            role,
            score=score,
            findings=[
                finding(
                    FeedbackSeverity.SHOULD_FIX,
                    f"{role.value} failure paths",
                    section=f"{3 + list(ReviewRole).index(role)}.1",
                )
            ],
        )
        return ProviderStructuredResult(
            value=value,
            usage=TokenUsage(input_tokens=10, output_tokens=10, total_tokens=20),
            model="mock-review-v1",
        )


async def test_regression_keeps_the_historical_best_without_rewriting_scores() -> None:
    manager = make_manager(provider=RegressingScoreProvider(delays_enabled=False))
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product whose third version regresses.",
            quality_threshold=85,
            max_iterations=3,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)
    scores = [version.evaluation.overall_score for version in result.versions]

    assert result.status is RunStatus.MAX_ITERATIONS_REACHED
    # Reviewer scores are stored exactly as given -- no max(old, new) clamping.
    assert scores == [66.7, 81.7, 78.3]
    assert result.best_version == 2
    assert result.best_score == 81.7
    # The best is explicitly *not* the last version.
    assert result.current_iteration == 3


async def test_terminal_payload_states_the_unmet_threshold_and_the_best_version() -> (
    None
):
    manager = make_manager(
        provider=RegressingScoreProvider(delays_enabled=False),
        # Three full versions of streamed deltas outgrow the 100-event default.
        settings=make_settings(event_buffer_size=1000),
    )
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product that never reaches its target.",
            quality_threshold=85,
            max_iterations=3,
        )
    )

    await manager.wait_for_completion(created.run_id, wait_seconds=5)
    events = manager.event_store.replay(created.run_id, 0)
    terminal = next(
        event for event in events if event.event is RunEventType.MAX_ITERATIONS_REACHED
    )

    assert terminal.payload["threshold_met"] is False
    assert terminal.payload["quality_threshold"] == 85
    assert terminal.payload["completed_iterations"] == 3
    assert terminal.payload["max_iterations"] == 3
    assert terminal.payload["best_version"] == 2
    assert terminal.payload["best_score"] == 81.7
    assert terminal.payload["final_version"] == 3
    assert terminal.payload["final_score"] == 78.3


async def test_scores_updated_carries_a_signed_delta_against_the_best() -> None:
    manager = make_manager(
        provider=RegressingScoreProvider(delays_enabled=False),
        # Three full versions of streamed deltas outgrow the 100-event default.
        settings=make_settings(event_buffer_size=1000),
    )
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product with a reported score delta.",
            quality_threshold=85,
            max_iterations=3,
        )
    )

    await manager.wait_for_completion(created.run_id, wait_seconds=5)
    events = manager.event_store.replay(created.run_id, 0)
    scored = [event for event in events if event.event is RunEventType.SCORES_UPDATED]

    assert [event.payload["delta_vs_best"] for event in scored] == [None, 15.0, -3.4]
    assert [event.payload["best_version"] for event in scored] == [1, 2, 2]


async def test_reaching_the_threshold_reports_a_met_target() -> None:
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product that clears its target score.",
            quality_threshold=85,
            max_iterations=3,
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)
    events = manager.event_store.replay(created.run_id, 0)
    terminal = next(
        event for event in events if event.event is RunEventType.RUN_COMPLETED
    )

    assert result.status is RunStatus.COMPLETED
    assert terminal.payload["threshold_met"] is True
    assert terminal.payload["best_version"] == result.best_version
    assert result.best_version == result.current_iteration


async def test_summary_list_exposes_the_best_version_for_the_sidebar() -> None:
    manager = make_manager(provider=RegressingScoreProvider(delays_enabled=False))
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="Build a product listed by its best version.",
            quality_threshold=85,
            max_iterations=3,
        )
    )
    await manager.wait_for_completion(created.run_id, wait_seconds=5)

    summary = next(
        item
        for item in await manager.list_runs(limit=10)
        if item.run_id == created.run_id
    )

    assert summary.best_version == 2
    assert summary.best_score == 81.7
    assert summary.latest_score == 78.3


class BaselineCapturingProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__(delays_enabled=False)
        self.baselines: list[str | None] = []
        self.languages: list[str] = []

    async def stream_prd(
        self,
        *,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan: RevisionPlan | None,
        baseline_prd: str | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> AsyncIterator[ProviderTextEvent]:
        self.baselines.append(baseline_prd)
        self.languages.append(output_language)
        async for event in super().stream_prd(
            user_idea=user_idea,
            target_audience=target_audience,
            user_constraints=user_constraints,
            iteration=iteration,
            revision_plan=revision_plan,
            baseline_prd=baseline_prd,
            output_language=output_language,
        ):
            yield event


async def test_generator_edits_the_best_version_rather_than_starting_over() -> None:
    provider = BaselineCapturingProvider()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a baseline-editing product.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    # First round has nothing to edit; every later round receives a document.
    assert provider.baselines[0] is None
    assert provider.baselines[1] == result.versions[0].content
    assert PRD_COMPLETION_MARKER not in (provider.baselines[1] or "")


async def test_unrelated_sections_stay_byte_identical_across_iterations() -> None:
    """The prompt contract asks for minimal edits; the mock must honour it too."""
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product with stable untouched sections.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    def section(content: str, heading: str) -> str:
        body = content.split(f"## {heading}\n", 1)[1]
        return body.split("\n## ", 1)[0]

    assert len(result.versions) >= 2
    first, second = result.versions[0].content, result.versions[1].content
    for heading in ("1. Product Overview", "2. Users and Scenarios", "4. Core Flow"):
        assert section(first, heading) == section(second, heading)


async def test_no_system_scaffolding_narration_reaches_the_document() -> None:
    manager = make_manager()
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product without process narration.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    for version in result.versions:
        assert "Applied revision plan" not in version.content
        assert "revision_plan" not in version.content


@pytest.mark.parametrize(
    ("idea", "expected"),
    [
        ("做一个播客按集付费的订阅产品，支持退款。", "zh"),
        ("Build a podcast micro-subscription product.", "en"),
        # A couple of stray CJK characters in an English brief stay English.
        ("Build a product for the 中国 market.", "en"),
    ],
)
def test_language_is_inferred_from_the_whole_brief(idea: str, expected: str) -> None:
    assert detect_output_language(idea, None, None) == expected


def test_unknown_language_code_falls_back_instead_of_raising() -> None:
    """A stale snapshot must not be able to fail a run."""
    assert "English" in language_directive("kl")


async def test_a_chinese_brief_pins_one_language_for_every_agent() -> None:
    provider = BaselineCapturingProvider()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(
            user_idea="做一个播客按集付费的订阅产品，需要覆盖退款与结算。",
            target_audience="播客听众",
        )
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.output_language == "zh"
    # Every generation attempt saw the same language: the three reviewers and the
    # optimizer read it off the same snapshot field.
    assert set(provider.languages) == {"zh"}


async def test_english_brief_stays_english() -> None:
    provider = BaselineCapturingProvider()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build an English-only podcast subscription.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.output_language == "en"
    assert set(provider.languages) == {"en"}


class NoUsageProvider(MockLLMProvider):
    async def stream_prd(
        self,
        *,
        user_idea: str,
        target_audience: str | None,
        user_constraints: str | None,
        iteration: int,
        revision_plan: RevisionPlan | None,
        baseline_prd: str | None = None,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> AsyncIterator[ProviderTextEvent]:
        del user_idea, target_audience, user_constraints, iteration
        del revision_plan, baseline_prd, output_language
        yield ProviderTextEvent(
            delta=f"# PRD\n\n## Scope\nComplete.\n{PRD_COMPLETION_MARKER}\n",
            model="mock-prd-v1",
        )


async def test_a_stream_without_usage_is_still_treated_as_a_failed_attempt() -> None:
    manager = make_manager(provider=NoUsageProvider(delays_enabled=False))
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a product with no reported usage.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == RetryableProviderError.code
