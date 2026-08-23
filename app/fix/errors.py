from __future__ import annotations

from enum import Enum


class FixErrorType(Enum):
    """Structured error types for the fix agent."""

    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    HALLUCINATION = "hallucination"
    SYNTAX_ERROR = "syntax_error"
    SEMANTIC_GUARD = "semantic_guard"
    DUPLICATE_PATCH = "duplicate_patch"
    NO_PROGRESS = "no_progress"
    TOKEN_BUDGET = "token_budget"
    LLM_CRASH = "llm_crash"
    PATCH_VALIDATION = "patch_validation"
    UNKNOWN = "unknown"


class FixError:
    """Structured error with type, message, and retryability."""

    def __init__(
        self,
        error_type: FixErrorType,
        message: str,
        retryable: bool = True,
        attempt: int = 0,
    ):
        self.type = error_type
        self.message = message
        self.retryable = retryable
        self.attempt = attempt

    def __str__(self) -> str:
        retryable = "retryable" if self.retryable else "terminal"
        return f"[{self.type.value}] ({retryable}) {self.message}"

    def __repr__(self) -> str:
        return (
            f"FixError(type={self.type.value!r}, "
            f"retryable={self.retryable}, "
            f"attempt={self.attempt})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, FixError):
            return NotImplemented
        return self.type == other.type and self.message == other.message

    def __hash__(self) -> int:
        return hash((self.type, self.message))


# Convenience constructors
def rate_limit_error(message: str, attempt: int = 0) -> FixError:
    return FixError(FixErrorType.RATE_LIMIT, message, retryable=True, attempt=attempt)


def timeout_error(message: str, attempt: int = 0) -> FixError:
    return FixError(FixErrorType.TIMEOUT, message, retryable=True, attempt=attempt)


def hallucination_error(message: str, attempt: int = 0) -> FixError:
    return FixError(FixErrorType.HALLUCINATION, message, retryable=True, attempt=attempt)


def syntax_error(message: str, attempt: int = 0) -> FixError:
    return FixError(FixErrorType.SYNTAX_ERROR, message, retryable=True, attempt=attempt)


def semantic_guard_error(message: str, attempt: int = 0) -> FixError:
    return FixError(FixErrorType.SEMANTIC_GUARD, message, retryable=True, attempt=attempt)


def duplicate_patch_error(message: str, attempt: int = 0) -> FixError:
    return FixError(FixErrorType.DUPLICATE_PATCH, message, retryable=False, attempt=attempt)


def no_progress_error(message: str, attempt: int = 0) -> FixError:
    return FixError(FixErrorType.NO_PROGRESS, message, retryable=False, attempt=attempt)


def token_budget_error(message: str, attempt: int = 0) -> FixError:
    return FixError(FixErrorType.TOKEN_BUDGET, message, retryable=False, attempt=attempt)


def llm_crash_error(message: str, attempt: int = 0) -> FixError:
    return FixError(FixErrorType.LLM_CRASH, message, retryable=True, attempt=attempt)


def patch_validation_error(message: str, attempt: int = 0) -> FixError:
    return FixError(FixErrorType.PATCH_VALIDATION, message, retryable=True, attempt=attempt)


def classify_error(exc: Exception, attempt: int = 0) -> FixError:
    """Classify an exception into a structured FixError type."""
    error_str = str(exc).lower()

    # Rate limit (check first since 429 is unambiguous)
    if "429" in error_str or "rate_limit" in error_str or "resource_exhausted" in error_str:
        return rate_limit_error(str(exc)[:500], attempt=attempt)

    # Token limit (check before timeout since "token" and "timeout" can overlap)
    if "context_length" in error_str or ("token" in error_str and "exceed" in error_str):
        return token_budget_error(str(exc)[:500], attempt=attempt)

    # Connection/HTTP status errors (check before generic timeout)
    if any(e in error_str for e in ["502", "503", "504"]):
        return llm_crash_error(str(exc)[:500], attempt=attempt)

    # Pure connection errors (not "connection timeout")
    if "connection" in error_str and "timeout" not in error_str:
        return llm_crash_error(str(exc)[:500], attempt=attempt)
    if "connect" in error_str and "timeout" not in error_str:
        return llm_crash_error(str(exc)[:500], attempt=attempt)

    # Timeout (generic, after HTTP status checks)
    if "timeout" in error_str or "timed out" in error_str:
        return timeout_error(str(exc)[:500], attempt=attempt)

    # Default
    return FixError(FixErrorType.UNKNOWN, str(exc)[:500], retryable=True, attempt=attempt)
