"""Authentication module — deep module exposing two FastAPI dependencies.

Public interface:
    ``require_auth``  — returns TokenPayload or raises 401.
    ``optional_auth`` — returns TokenPayload or None, never raises.

When ``settings.auth_enabled`` is False both dependencies return an anonymous
admin payload so the development workflow is unbroken.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings
from .token_factory import TokenPayload, decode_token
from ..exceptions import AuthenticationError

logger = logging.getLogger(__name__)

# HTTPBearer with auto_error=False so we can distinguish "no token" from "bad token".
_bearer_scheme = HTTPBearer(auto_error=False)

# Re-usable anonymous payload for dev mode.
_ANONYMOUS = TokenPayload(sub="anonymous", role="admin", exp=datetime.max.replace(tzinfo=timezone.utc))


def get_bearer_scheme() -> HTTPBearer:
    """Expose the security scheme so OpenAPI picks it up."""
    return _bearer_scheme


def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> TokenPayload:
    """FastAPI dependency: require a valid JWT.

    When ``AUTH_ENABLED=false`` (default), returns an anonymous admin payload
    so all requests succeed without a token.
    """
    if not settings.auth_enabled:
        return _ANONYMOUS

    if credentials is None:
        raise AuthenticationError("Missing authentication token")

    payload = decode_token(credentials.credentials, settings.jwt_secret_key, settings.jwt_algorithm)
    if payload is None:
        raise AuthenticationError("Invalid or expired token")

    return payload


def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[TokenPayload]:
    """FastAPI dependency: validate a token if present, return None otherwise.

    Never raises — used on read endpoints where auth is informational.
    When ``AUTH_ENABLED=false``, returns the anonymous payload.
    """
    if not settings.auth_enabled:
        return _ANONYMOUS

    if credentials is None:
        return None

    return decode_token(credentials.credentials, settings.jwt_secret_key, settings.jwt_algorithm)
