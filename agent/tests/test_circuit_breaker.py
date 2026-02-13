"""Tests for circuit breaker state machine.

Tests the public interface: check(), record_success(), record_failure(),
and the composed run_with_timeout() helper. Validates state transitions:
  CLOSED → OPEN (after threshold failures)
  OPEN → HALF_OPEN (after cooldown)
  HALF_OPEN → CLOSED (on success)
  HALF_OPEN → OPEN (on failure)
"""

import time
from unittest.mock import patch

import pytest

from circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    get_breaker,
    reset_all,
    run_with_timeout,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset global breaker registry between tests."""
    reset_all()
    yield
    reset_all()


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


class TestCircuitBreakerStates:
    def test_starts_closed(self):
        cb = CircuitBreaker("test-endpoint")
        assert cb.state == CircuitState.CLOSED

    def test_stays_closed_under_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_opens_at_threshold(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_blocks_requests(self):
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=60)
        cb.record_failure()
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            cb.check()
        assert exc_info.value.endpoint == "test"
        assert exc_info.value.retry_after > 0

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        # One more failure should NOT open (count was reset)
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_open_transitions_to_half_open_after_cooldown(self):
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=0.01)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.02)
        cb.check()  # Should not raise — transitions to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_closes_on_success(self):
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.check()  # → HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        cb = CircuitBreaker("test", failure_threshold=1, cooldown_seconds=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.check()  # → HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


# ---------------------------------------------------------------------------
# Global registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_get_breaker_creates_new(self):
        b = get_breaker("model-a")
        assert b.endpoint == "model-a"
        assert b.state == CircuitState.CLOSED

    def test_get_breaker_returns_same_instance(self):
        b1 = get_breaker("model-a")
        b2 = get_breaker("model-a")
        assert b1 is b2

    def test_different_endpoints_get_different_breakers(self):
        b1 = get_breaker("model-a")
        b2 = get_breaker("model-b")
        assert b1 is not b2

    def test_reset_all_clears_registry(self):
        b1 = get_breaker("model-a")
        b1.record_failure()
        reset_all()
        b2 = get_breaker("model-a")
        assert b2.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# run_with_timeout
# ---------------------------------------------------------------------------


class TestRunWithTimeout:
    def test_success_returns_result(self):
        result = run_with_timeout(lambda: 42, timeout=5, label="test")
        assert result == 42

    def test_timeout_raises_and_opens_circuit(self):
        def slow():
            time.sleep(10)

        with pytest.raises(TimeoutError):
            run_with_timeout(slow, timeout=0.1, label="slow-endpoint")

        # Circuit should record the failure
        b = get_breaker("slow-endpoint")
        assert b._failure_count >= 1

    def test_exception_propagates_and_records_failure(self):
        def failing():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            run_with_timeout(failing, timeout=5, label="fail-endpoint")

        b = get_breaker("fail-endpoint")
        assert b._failure_count >= 1

    def test_blocked_by_open_circuit(self):
        b = get_breaker("blocked")
        # Force open
        for _ in range(3):
            b.record_failure()

        with pytest.raises(CircuitBreakerOpen):
            run_with_timeout(lambda: 1, timeout=5, label="blocked")
