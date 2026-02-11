"""Request context middleware — single deep middleware for observability and rate limiting.

Responsibilities (all handled in one pass, not separate middlewares):
- Generate or propagate ``X-Request-ID`` header
- Measure request duration
- Log every request/response as structured JSON
- Enforce per-client rate limiting via token bucket

The rate limiter is a pure function ``check_rate_limit`` that can be tested independently.
"""

import logging
import threading
import time
import uuid
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..core.config import settings
from ..core.logging_config import request_id_var

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiting — pure function + in-memory bucket
# ---------------------------------------------------------------------------

# Bucket state: {client_key: (available_tokens, last_refill_timestamp)}
_rate_buckets: dict[str, tuple[float, float]] = {}
_rate_lock = threading.Lock()

# Periodic eviction to prevent unbounded memory growth from rotating IPs.
_rate_call_count = 0
_EVICT_EVERY = 100       # sweep every N calls
_EVICT_AGE = 120.0       # remove entries older than 2 minutes


def check_rate_limit(
    bucket: dict[str, tuple[float, float]],
    key: str,
    max_per_minute: int,
    now: Optional[float] = None,
) -> tuple[bool, float]:
    """Check whether a request from *key* is allowed under the token bucket.

    Args:
        bucket: Mutable dict holding per-key state. Modified in place.
        key: Client identifier (IP address or token subject).
        max_per_minute: Sustained rate cap.
        now: Current timestamp (injectable for testing). Defaults to ``time.monotonic()``.

    Returns:
        ``(allowed, retry_after)`` — *retry_after* is 0.0 when allowed, otherwise
        the number of seconds until the next token becomes available.
    """
    global _rate_call_count

    if max_per_minute <= 0:
        return True, 0.0

    if now is None:
        now = time.monotonic()

    # Periodic eviction of stale entries to bound memory usage.
    _rate_call_count += 1
    if _rate_call_count % _EVICT_EVERY == 0:
        cutoff = now - _EVICT_AGE
        stale = [k for k, (_, ts) in bucket.items() if ts < cutoff]
        for k in stale:
            del bucket[k]

    refill_rate = max_per_minute / 60.0  # tokens per second

    if key in bucket:
        tokens, last_refill = bucket[key]
        elapsed = now - last_refill
        tokens = min(max_per_minute, tokens + elapsed * refill_rate)
    else:
        tokens = float(max_per_minute)
        last_refill = now

    if tokens >= 1.0:
        bucket[key] = (tokens - 1.0, now)
        return True, 0.0

    retry_after = (1.0 - tokens) / refill_rate
    bucket[key] = (tokens, now)
    return False, retry_after


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

# Paths that bypass rate limiting (health probes should never be throttled).
_EXEMPT_PATHS = frozenset({"/", "/health", "/health/deep", "/docs", "/redoc", "/openapi.json"})


def _client_key(request: Request) -> str:
    """Derive a rate-limit key from the request.

    Uses the ``X-Forwarded-For`` header when behind a proxy, otherwise the
    direct client IP.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Single middleware handling request-id, timing, logging, and rate limiting."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # --- Request ID ---
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request_id_var.set(rid)

        # --- Rate limiting ---
        if request.url.path not in _EXEMPT_PATHS:
            key = _client_key(request)
            with _rate_lock:
                allowed, retry_after = check_rate_limit(
                    _rate_buckets, key, settings.rate_limit_per_minute
                )
            if not allowed:
                logger.warning(
                    "Rate limit exceeded",
                    extra={"client": key, "path": request.url.path, "retry_after": round(retry_after, 1)},
                )
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "RATE_LIMITED",
                        "message": "Too many requests",
                        "details": {"retry_after": round(retry_after, 1)},
                    },
                    headers={
                        "Retry-After": str(int(retry_after) + 1),
                        "X-Request-ID": rid,
                    },
                )

        # --- Timing ---
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        # --- Response headers ---
        response.headers["X-Request-ID"] = rid
        response.headers["X-Response-Time"] = f"{duration_ms}ms"

        # --- Structured request log ---
        logger.info(
            f"{request.method} {request.url.path} {response.status_code}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response
