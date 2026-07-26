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
    code = "PROVIDER_ERROR"
    retryable = False


class RetryableProviderError(ProviderError):
    code = "PROVIDER_TEMPORARY_ERROR"
    retryable = True


class ProviderAuthenticationError(ProviderError):
    code = "PROVIDER_AUTHENTICATION_FAILED"


class InvalidModelError(ProviderError):
    code = "PROVIDER_MODEL_INVALID"


class ProviderUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "PROVIDER_UNAVAILABLE",
            "The configured LLM provider is not available.",
            503,
        )
