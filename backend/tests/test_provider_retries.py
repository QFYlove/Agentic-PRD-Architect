from __future__ import annotations

import pytest

from backend.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderForbiddenError,
    ProviderInsufficientBalanceError,
    ProviderRequestRejectedError,
    RetryableProviderError,
)
from backend.language import DEFAULT_OUTPUT_LANGUAGE
from backend.providers.base import ProviderStructuredResult
from backend.providers.mock import MockLLMProvider
from backend.schemas import (
    CreateRunRequest,
    ReviewRole,
    RunStatus,
    TokenUsage,
)
from backend.tests.helpers import make_manager


class InvalidThenRepairProvider(MockLLMProvider):
    def __init__(self, *, repair_valid: bool = True) -> None:
        super().__init__(delays_enabled=False)
        self.original_calls = 0
        self.repair_calls = 0
        self.repair_valid = repair_valid

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> ProviderStructuredResult:
        self.original_calls += 1
        if role is ReviewRole.TECH and iteration == 1:
            return ProviderStructuredResult(
                value={"role": "tech", "score": 999},
                usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
                model="invalid",
            )
        return await super().generate_review(
            role=role,
            prd=prd,
            iteration=iteration,
            output_language=output_language,
        )

    async def repair_structured(self, **kwargs: object) -> ProviderStructuredResult:
        self.repair_calls += 1
        if not self.repair_valid:
            return ProviderStructuredResult(
                value={"still": "invalid"},
                usage=TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2),
                model="invalid-repair",
            )
        return await super().repair_structured(**kwargs)


async def test_invalid_structure_uses_one_repair_without_repeating_original() -> None:
    provider = InvalidThenRepairProvider()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a structured retry product.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert provider.repair_calls == 1
    assert provider.original_calls == 6


async def test_second_invalid_structure_fails_without_extra_calls() -> None:
    provider = InvalidThenRepairProvider(repair_valid=False)
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a failing structured product.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "STRUCTURED_OUTPUT_INVALID"
    assert provider.original_calls == 3
    assert provider.repair_calls == 1


class TransportRetryProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__(delays_enabled=False)
        self.tech_calls = 0

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> ProviderStructuredResult:
        if role is ReviewRole.TECH and iteration == 1:
            self.tech_calls += 1
            if self.tech_calls == 1:
                raise RetryableProviderError("temporary")
        return await super().generate_review(
            role=role,
            prd=prd,
            iteration=iteration,
            output_language=output_language,
        )


async def test_retryable_transport_error_retries_original_once() -> None:
    provider = TransportRetryProvider()
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a transport retry product.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.COMPLETED
    assert provider.tech_calls == 2


class AuthenticationFailureProvider(MockLLMProvider):
    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> ProviderStructuredResult:
        del role, prd, iteration, output_language
        raise ProviderAuthenticationError("invalid credentials")


async def test_authentication_error_is_not_retried_or_exposed() -> None:
    provider = AuthenticationFailureProvider(delays_enabled=False)
    manager = make_manager(provider=provider)
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build an authentication failure product.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == "PROVIDER_AUTHENTICATION_FAILED"
    assert "credentials" not in result.error.message


class RaisingReviewProvider(MockLLMProvider):
    def __init__(self, error: ProviderError) -> None:
        super().__init__(delays_enabled=False)
        self.error = error

    async def generate_review(
        self,
        *,
        role: ReviewRole,
        prd: str,
        iteration: int,
        output_language: str = DEFAULT_OUTPUT_LANGUAGE,
    ) -> ProviderStructuredResult:
        del role, prd, iteration, output_language
        raise self.error


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (
            ProviderInsufficientBalanceError("balance for account acct_secret is 0"),
            "PROVIDER_INSUFFICIENT_BALANCE",
            False,
        ),
        (
            ProviderForbiddenError("region blocked for key sk-secret"),
            "PROVIDER_FORBIDDEN",
            False,
        ),
        (
            ProviderRequestRejectedError("payload rejected: internal-prompt-dump"),
            "PROVIDER_REQUEST_REJECTED",
            False,
        ),
        (
            RetryableProviderError("upstream 503 at pod-secret-7"),
            "PROVIDER_TEMPORARY_ERROR",
            True,
        ),
    ],
)
async def test_provider_errors_keep_their_code_instead_of_workflow_failed(
    error: ProviderError,
    code: str,
    retryable: bool,
) -> None:
    manager = make_manager(provider=RaisingReviewProvider(error))
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build a provider error mapping product.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.status is RunStatus.FAILED
    assert result.error is not None
    assert result.error.code == code
    assert result.error.retryable is retryable
    assert result.error.message == error.user_message
    assert "secret" not in result.error.message


async def test_unknown_provider_subclass_still_avoids_generic_failure() -> None:
    class UnmappedProviderError(ProviderError):
        code = "PROVIDER_ERROR"

    manager = make_manager(provider=RaisingReviewProvider(UnmappedProviderError("x")))
    created = await manager.create_run(
        CreateRunRequest(user_idea="Build an unmapped provider error product.")
    )

    result = await manager.wait_for_completion(created.run_id, wait_seconds=5)

    assert result.error is not None
    assert result.error.code == "PROVIDER_ERROR"
    assert result.error.retryable is False
