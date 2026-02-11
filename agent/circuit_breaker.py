"""Thread-safe circuit breaker for LLM endpoint protection.

Prevents cascading timeouts when an LLM endpoint is down by tracking
consecutive failures and short-circuiting requests during outages.

States:
  CLOSED    -- normal operation, requests pass through
  OPEN      -- endpoint is down, requests fail immediately
  HALF_OPEN -- cooldown expired, one probe request allowed

Also provides ``run_with_timeout`` which combines a wall-clock timeout
with circuit-breaker bookkeeping so callers get a single helper.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("isocrates.agent.circuit_breaker")

# Defaults — can be overridden per instance.
DEFAULT_FAILURE_THRESHOLD = 3    # consecutive failures before opening
DEFAULT_COOLDOWN_SECONDS = 60    # seconds to wait before half-open probe


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when the circuit is open and requests are blocked."""

    def __init__(self, endpoint: str, retry_after: float):
        self.endpoint = endpoint
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker OPEN for '{endpoint}'. "
            f"Retry after {retry_after:.0f}s."
        )


class CircuitBreaker:
    """Per-endpoint circuit breaker.

    Thread-safe: uses a Lock so concurrent scouts/writers can share
    a single breaker per model endpoint.
    """

    def __init__(
        self,
        endpoint: str,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS,
    ) -> None:
        self.endpoint = endpoint
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def check(self) -> None:
        """Check if a request is allowed. Raises CircuitBreakerOpen if not."""
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self._cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    logger.info("Circuit %s: OPEN -> HALF_OPEN (cooldown expired)", self.endpoint)
                    return
                raise CircuitBreakerOpen(self.endpoint, self._cooldown_seconds - elapsed)
            # HALF_OPEN: allow the probe request through
            return

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info("Circuit %s: HALF_OPEN -> CLOSED", self.endpoint)
            else:
                self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit %s: HALF_OPEN -> OPEN (probe failed)", self.endpoint)
            elif self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit %s: CLOSED -> OPEN (%d consecutive failures)",
                    self.endpoint, self._failure_count,
                )


# ---------------------------------------------------------------------------
# Global registry — one breaker per model endpoint
# ---------------------------------------------------------------------------

_breakers: dict[str, CircuitBreaker] = {}
_registry_lock = threading.Lock()


def get_breaker(endpoint: str) -> CircuitBreaker:
    """Get or create a circuit breaker for a model endpoint."""
    with _registry_lock:
        if endpoint not in _breakers:
            _breakers[endpoint] = CircuitBreaker(endpoint=endpoint)
        return _breakers[endpoint]


def reset_all() -> None:
    """Reset all circuit breakers (for testing)."""
    with _registry_lock:
        _breakers.clear()


# ---------------------------------------------------------------------------
# Timeout helper
# ---------------------------------------------------------------------------

def run_with_timeout(
    fn: Callable[[], Any],
    timeout: int,
    label: str = "conversation",
) -> Any:
    """Run *fn* with a wall-clock timeout and circuit-breaker bookkeeping.

    Wraps *fn* in a single-thread executor to enforce the timeout.
    Records success/failure on the circuit breaker for *label*.

    Raises:
        CircuitBreakerOpen: if the circuit for *label* is open.
        TimeoutError: if *fn* exceeds *timeout* seconds.
        Exception: any exception raised by *fn*.
    """
    breaker = get_breaker(label)
    breaker.check()  # raises CircuitBreakerOpen if open

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)
        try:
            result = future.result(timeout=timeout)
            breaker.record_success()
            return result
        except FuturesTimeoutError:
            breaker.record_failure()
            logger.error(
                "%s timed out after %ds", label, timeout,
            )
            raise TimeoutError(f"{label} exceeded {timeout}s timeout")
        except Exception:
            breaker.record_failure()
            raise
