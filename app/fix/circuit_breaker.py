"""Circuit breaker pattern for multi-LLM fallback.

Design:
- Route traffic through a chain of LLM providers
- When a provider hits 429 rate limit or fails, circuit opens → try next provider
- After recovery timeout, circuit half-opens → try once more
- Prevents cascade failures during traffic spikes

Providers are tried in order. The first successful response wins.
"""

from __future__ import annotations

import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # normal operation — traffic flows
    OPEN = "open"  # failing — skip this provider
    HALF_OPEN = "half_open"  # testing recovery — try once


class CircuitBreaker:
    """Per-provider circuit breaker.

    After ``failure_threshold`` consecutive failures, the circuit opens
    and skips the provider for ``recovery_timeout`` seconds.
    """

    def __init__(
        self, failure_threshold: int = 3, recovery_timeout: float = 60.0
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failures: dict[str, int] = {}
        self._last_failure: dict[str, float] = {}
        self._state: dict[str, CircuitState] = {}

    def record_success(self, provider: str) -> None:
        """Record a successful call — close the circuit."""
        self._failures[provider] = 0
        self._state[provider] = CircuitState.CLOSED

    def record_failure(self, provider: str) -> None:
        """Record a failed call — may open the circuit."""
        self._failures[provider] = self._failures.get(provider, 0) + 1
        self._last_failure[provider] = time.time()
        if self._failures[provider] >= self.failure_threshold:
            self._state[provider] = CircuitState.OPEN
            logger.warning(
                "Circuit OPEN for provider '%s' after %d failures",
                provider,
                self._failures[provider],
            )

    def should_try(self, provider: str) -> bool:
        """Return True if we should attempt a call to this provider."""
        state = self._state.get(provider, CircuitState.CLOSED)
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure.get(provider, 0)
            if elapsed > self.recovery_timeout:
                self._state[provider] = CircuitState.HALF_OPEN
                logger.info(
                    "Circuit HALF_OPEN for provider '%s' after %.1fs",
                    provider,
                    elapsed,
                )
                return True
            return False
        # HALF_OPEN: allow one attempt
        return True

    def get_state(self, provider: str) -> CircuitState:
        return self._state.get(provider, CircuitState.CLOSED)

    def reset(self, provider: str) -> None:
        """Manually reset a provider's circuit."""
        self._failures.pop(provider, None)
        self._state.pop(provider, None)
        self._last_failure.pop(provider, None)

    def reset_all(self) -> None:
        """Reset all providers."""
        self._failures.clear()
        self._state.clear()
        self._last_failure.clear()


class MultiLLMRouter:
    """Routes LLM calls through a circuit breaker with fallback chain.

    Usage::

        router = MultiLLMRouter([
            ("openai", openai_client),
            ("gemini", gemini_client),
            ("openrouter", openrouter_client),
        ])
        response = router.invoke(prompt)
    """

    def __init__(
        self,
        providers: list[tuple[str, object]],
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.providers = providers
        self.breaker = CircuitBreaker(failure_threshold, recovery_timeout)

    def invoke(self, prompt: str, **kwargs: object) -> object:
        """Invoke the first available LLM provider.

        Tries providers in order. Returns the first successful response.
        Raises RuntimeError if all providers are exhausted.
        """
        last_error: Exception | None = None

        for name, client in self.providers:
            if not self.breaker.should_try(name):
                logger.debug("Skipping provider '%s' (circuit open)", name)
                continue

            try:
                response = client.invoke(prompt, **kwargs)  # type: ignore[union-attr]
                self.breaker.record_success(name)
                return response
            except Exception as exc:
                self.breaker.record_failure(name)
                last_error = exc
                # Rate limit errors → try next provider immediately
                if _is_rate_limit(exc):
                    logger.warning(
                        "Provider '%s' rate limited, trying next", name
                    )
                    continue
                # Non-rate-limit errors propagate
                raise

        raise RuntimeError(
            f"All LLM providers exhausted. Last error: {last_error}"
        )

    def get_provider_states(self) -> dict[str, str]:
        """Return the current circuit state for each provider."""
        return {
            name: self.breaker.get_state(name).value
            for name, _ in self.providers
        }


def _is_rate_limit(exc: Exception) -> bool:
    """Check if an exception is a rate limit error."""
    msg = str(exc).lower()
    indicators = ["429", "rate limit", "too many requests", "quota exceeded"]
    return any(indicator in msg for indicator in indicators)
