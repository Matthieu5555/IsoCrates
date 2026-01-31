"""Tests for the rate limiting pure function and middleware integration."""

from app.middleware.request_context import check_rate_limit


class TestCheckRateLimit:
    """Unit tests for the pure function — no middleware, no HTTP."""

    def test_allows_within_limit(self):
        bucket: dict = {}
        allowed, retry = check_rate_limit(bucket, "client-a", max_per_minute=60, now=0.0)
        assert allowed is True
        assert retry == 0.0

    def test_denies_after_exhaustion(self):
        bucket: dict = {}
        now = 0.0
        # Exhaust all tokens
        for _ in range(60):
            check_rate_limit(bucket, "client-a", max_per_minute=60, now=now)

        allowed, retry = check_rate_limit(bucket, "client-a", max_per_minute=60, now=now)
        assert allowed is False
        assert retry > 0

    def test_refills_over_time(self):
        bucket: dict = {}
        # Exhaust tokens at t=0
        for _ in range(60):
            check_rate_limit(bucket, "client-a", max_per_minute=60, now=0.0)

        # 2 seconds later: should have refilled ~2 tokens
        allowed, _ = check_rate_limit(bucket, "client-a", max_per_minute=60, now=2.0)
        assert allowed is True

    def test_separate_keys_independent(self):
        bucket: dict = {}
        for _ in range(60):
            check_rate_limit(bucket, "client-a", max_per_minute=60, now=0.0)

        # Different client should still have tokens
        allowed, _ = check_rate_limit(bucket, "client-b", max_per_minute=60, now=0.0)
        assert allowed is True

    def test_zero_limit_always_allows(self):
        bucket: dict = {}
        allowed, _ = check_rate_limit(bucket, "any", max_per_minute=0, now=0.0)
        assert allowed is True
