from __future__ import annotations


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class RunNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__("RUN_NOT_FOUND", "The requested run does not exist.", 404)


class RunConflictError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, 409)


class RunCapacityError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "RUN_CAPACITY_REACHED",
            "The local concurrent run limit has been reached.",
            429,
        )


class StoreCapacityError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "STORE_CAPACITY_REACHED",
            "The local retained run limit has been reached.",
            429,
        )


class EventExpiredError(AppError):
    def __init__(self, oldest_sequence: int) -> None:
        super().__init__(
            "EVENTS_EXPIRED",
            f"Requested events are no longer buffered; oldest is {oldest_sequence}.",
            410,
        )


class ProviderError(Exception):
    """A provider failure already translated into a safe, stable contract.

    ``code`` and ``user_message`` are the only things that reach the client, so
    raw provider text (which can echo keys, prompts, or account details) never
    leaves the backend.
    """

    code = "PROVIDER_ERROR"
    retryable = False
    user_message = "The configured provider could not complete the request."


class RetryableProviderError(ProviderError):
    code = "PROVIDER_TEMPORARY_ERROR"
    retryable = True
    user_message = "The provider remained unavailable after retry."


class ProviderAuthenticationError(ProviderError):
    code = "PROVIDER_AUTHENTICATION_FAILED"
    user_message = "The configured provider rejected the request."


class InvalidModelError(ProviderError):
    code = "PROVIDER_MODEL_INVALID"
    user_message = "The configured provider rejected the request."


class ProviderInsufficientBalanceError(ProviderError):
    code = "PROVIDER_INSUFFICIENT_BALANCE"
    user_message = "The provider account has insufficient balance or quota."


class ProviderForbiddenError(ProviderError):
    code = "PROVIDER_FORBIDDEN"
    user_message = "The provider denied access to the configured model."


class ProviderRequestRejectedError(ProviderError):
    code = "PROVIDER_REQUEST_REJECTED"
    user_message = "The provider rejected the request payload."


class ProviderIncompleteOutputError(RetryableProviderError):
    """The model stopped before finishing the document.

    Retryable on purpose: every subclass below describes a stop that a second
    attempt can succeed at. The generator's existing retry loop handles them, and
    a truncated body never becomes a ``PRDVersion``.

    The subclasses exist because the three causes need different words in front
    of a user: an output cap is a document-too-long problem, a missing end marker
    is the model quitting early, and a resource rejection is the service being
    unwell. Collapsing them into one code made every one of them read as
    「操作失败，请稍后重试」. The base code stays valid so runs recorded before
    the split still resolve to a message.
    """

    code = "PROVIDER_OUTPUT_INCOMPLETE"
    retryable = True
    user_message = "The provider returned an incomplete document."


class ProviderOutputTruncatedError(ProviderIncompleteOutputError):
    """The output cap cut the document off (``finish_reason`` length/max_tokens)."""

    code = "PROVIDER_OUTPUT_TRUNCATED"
    user_message = "The provider hit its output limit before finishing."


class ProviderOutputUnfinishedError(ProviderIncompleteOutputError):
    """The provider reported a clean stop on a document that is not finished.

    This is the case ``finish_reason`` cannot catch on its own: the stream ended
    with ``stop``, or ended without any reason at all, but the completion marker
    the generator is told to write as its last line never arrived.
    """

    code = "PROVIDER_OUTPUT_UNFINISHED"
    user_message = "The provider stopped before the document was finished."


class ProviderOutputInterruptedError(ProviderIncompleteOutputError):
    """The provider itself broke off -- a resource rejection or an unknown stop.

    ``insufficient_system_resource`` is the named case; an unrecognised
    ``finish_reason`` lands here too, because a provider inventing a new stop
    reason is reporting a problem rather than a clean finish.
    """

    code = "PROVIDER_OUTPUT_INTERRUPTED"
    user_message = "The provider interrupted the generation."


class ProviderContentFilteredError(ProviderError):
    """The provider's own safety filter stopped the completion.

    Not retryable: the same prompt filtered once will be filtered again, so
    burning a second call only delays the same failure.
    """

    code = "PROVIDER_CONTENT_FILTERED"
    retryable = False
    user_message = "The provider blocked this request's content."


class ProviderUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "PROVIDER_UNAVAILABLE",
            "The configured LLM provider is not available.",
            503,
        )
