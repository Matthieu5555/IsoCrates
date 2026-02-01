"""Authentication module — deep module exposing FastAPI dependencies.

Public interface:
    ``require_auth``  — returns AuthContext or raises 401.
    ``optional_auth`` — returns AuthContext or None, never raises.
    ``require_admin`` — returns AuthContext, raises 403 if not admin.

When ``settings.auth_enabled`` is False all dependencies return an anonymous
admin context with a root grant so the development workflow is unbroken.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .token_factory import TokenPayload, decode_token
from ..database import get_db
from ..exceptions import AuthenticationError, ForbiddenError

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    """Resolved authentication context available to every endpoint.

    Contains the authenticated user's identity, global role, and
    folder grants. Endpoints pass this to permission_service.check_permission().
    """

    user_id: str
    role: str
    grants: list = field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_service_account(self) -> bool:
        return self.role == "service"


# Dev-mode anonymous context: admin with root grant.
# Uses a stub object for the grant to avoid importing the ORM model at module level.
class _StubGrant:
    """Lightweight stand-in for FolderGrant used only in dev mode."""

    def __init__(self, path_prefix: str, role: str):
        self.path_prefix = path_prefix
        self.role = role


_ANONYMOUS = AuthContext(
    user_id="anonymous",
    role="admin",
    grants=[_StubGrant(path_prefix="", role="admin")],
)


def get_bearer_scheme() -> HTTPBearer:
    """Expose the security scheme so OpenAPI picks it up."""
    return _bearer_scheme


def require_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> AuthContext:
    """Require a valid JWT and return the user's AuthContext.

    When ``AUTH_ENABLED=false`` returns anonymous admin context.
    """
    if not settings.auth_enabled:
        return _ANONYMOUS

    if credentials is None:
        raise AuthenticationError("Missing authentication token")

    payload = decode_token(
        credentials.credentials, settings.jwt_secret_key, settings.jwt_algorithm
    )
    if payload is None:
        raise AuthenticationError("Invalid or expired token")

    return _load_auth_context(payload, db)


def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[AuthContext]:
    """Validate a token if present, return None otherwise. Never raises."""
    if not settings.auth_enabled:
        return _ANONYMOUS

    if credentials is None:
        return None

    payload = decode_token(
        credentials.credentials, settings.jwt_secret_key, settings.jwt_algorithm
    )
    if payload is None:
        return None

    return _load_auth_context(payload, db)


def require_admin(
    auth: AuthContext = Depends(require_auth),
) -> AuthContext:
    """Require the authenticated user to be an admin. Raises 403 otherwise."""
    if not auth.is_admin:
        raise ForbiddenError("Admin access required")
    return auth


def _load_auth_context(payload: TokenPayload, db: Session) -> AuthContext:
    """Load user and grants from DB given a decoded token payload."""
    from ..models.user import User, FolderGrant

    user = db.query(User).filter(User.user_id == payload.sub).first()
    if user is None:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise AuthenticationError("Account is deactivated")

    grants = db.query(FolderGrant).filter(FolderGrant.user_id == user.user_id).all()

    return AuthContext(
        user_id=user.user_id,
        role=user.role,
        grants=grants,
    )
