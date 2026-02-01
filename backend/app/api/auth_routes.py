"""Authentication and user management API endpoints.

Public endpoints:
    POST /api/auth/register  — create account (open for first user, admin-only after)
    POST /api/auth/login     — authenticate and receive JWT
    GET  /api/auth/me        — current user info + grants

Admin-only endpoints:
    GET    /api/auth/users                           — list all users
    PUT    /api/auth/users/{user_id}/role             — change global role
    PUT    /api/auth/users/{user_id}/deactivate       — deactivate account
    POST   /api/auth/users/{user_id}/grants           — add folder grant
    DELETE /api/auth/users/{user_id}/grants/{path}    — revoke folder grant
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.auth import AuthContext, require_auth, require_admin
from ..core.config import settings
from ..core.token_factory import create_token
from ..database import get_db
from ..services import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


# --- Request/Response schemas ---


class RegisterRequest(BaseModel):
    email: str = Field(..., description="Email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")
    display_name: str = Field(..., description="Display name")

    model_config = {
        "json_schema_extra": {
            "examples": [{"email": "alice@company.com", "password": "securepass", "display_name": "Alice"}]
        }
    }


class LoginRequest(BaseModel):
    email: str
    password: str


class GrantRequest(BaseModel):
    path_prefix: str = Field("", description="Path prefix (empty string for root access)")
    role: str = Field("viewer", description="Role: admin, editor, or viewer")


class RoleRequest(BaseModel):
    role: str = Field(..., description="New role: admin, editor, or viewer")


class GrantResponse(BaseModel):
    path_prefix: str
    role: str

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    user_id: str
    display_name: str
    email: Optional[str] = None
    role: str
    is_active: bool
    grants: List[GrantResponse] = []

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    token: str
    user: UserResponse


class MeResponse(BaseModel):
    user: UserResponse


# --- Endpoints ---

from ..core.auth import optional_auth


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    summary="Register a new user",
    description="First registration is open (creates admin). After that, admin auth required.",
)
def register_user(
    body: RegisterRequest,
    db: Session = Depends(get_db),
    auth: Optional[AuthContext] = Depends(optional_auth),
):
    from ..models.user import User
    from ..exceptions import ForbiddenError

    real_user_count = db.query(User).filter(User.email.isnot(None)).count()

    if real_user_count > 0:
        if auth is None or not auth.is_admin:
            raise ForbiddenError("Only admins can register new users")

    user = auth_service.register_user(
        db, body.email, body.password, body.display_name
    )
    grants = auth_service.get_user_grants(db, user.user_id)
    return UserResponse(
        user_id=user.user_id,
        display_name=user.display_name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        grants=[GrantResponse(path_prefix=g.path_prefix, role=g.role) for g in grants],
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate and receive JWT",
)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, body.email, body.password)
    token = create_token(
        subject=user.user_id,
        role=user.role,
        secret=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    grants = auth_service.get_user_grants(db, user.user_id)
    return LoginResponse(
        token=token,
        user=UserResponse(
            user_id=user.user_id,
            display_name=user.display_name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            grants=[GrantResponse(path_prefix=g.path_prefix, role=g.role) for g in grants],
        ),
    )


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current user info and grants",
)
def get_me(auth: AuthContext = Depends(require_auth), db: Session = Depends(get_db)):
    user = auth_service.get_user_by_id(db, auth.user_id)
    if user is None:
        from ..exceptions import AuthenticationError
        raise AuthenticationError("User not found")
    grants = auth_service.get_user_grants(db, auth.user_id)
    return MeResponse(
        user=UserResponse(
            user_id=user.user_id,
            display_name=user.display_name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            grants=[GrantResponse(path_prefix=g.path_prefix, role=g.role) for g in grants],
        ),
    )


@router.get(
    "/users",
    response_model=List[UserResponse],
    summary="List all users (admin only)",
)
def list_users(
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = auth_service.list_users(db)
    result = []
    for u in users:
        grants = auth_service.get_user_grants(db, u.user_id)
        result.append(
            UserResponse(
                user_id=u.user_id,
                display_name=u.display_name,
                email=u.email,
                role=u.role,
                is_active=u.is_active,
                grants=[GrantResponse(path_prefix=g.path_prefix, role=g.role) for g in grants],
            )
        )
    return result


@router.put(
    "/users/{user_id}/role",
    response_model=UserResponse,
    summary="Change a user's global role (admin only)",
)
def update_role(
    user_id: str,
    body: RoleRequest,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = auth_service.update_user_role(db, user_id, body.role)
    grants = auth_service.get_user_grants(db, user.user_id)
    return UserResponse(
        user_id=user.user_id,
        display_name=user.display_name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        grants=[GrantResponse(path_prefix=g.path_prefix, role=g.role) for g in grants],
    )


@router.put(
    "/users/{user_id}/deactivate",
    response_model=UserResponse,
    summary="Deactivate a user account (admin only)",
)
def deactivate(
    user_id: str,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    user = auth_service.deactivate_user(db, user_id)
    return UserResponse(
        user_id=user.user_id,
        display_name=user.display_name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        grants=[],
    )


@router.post(
    "/users/{user_id}/grants",
    response_model=GrantResponse,
    status_code=201,
    summary="Add or update a folder grant (admin only)",
)
def add_grant(
    user_id: str,
    body: GrantRequest,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    grant = auth_service.create_grant(
        db, user_id, body.path_prefix, body.role, granted_by=auth.user_id
    )
    return GrantResponse(path_prefix=grant.path_prefix, role=grant.role)


@router.delete(
    "/users/{user_id}/grants/{path_prefix:path}",
    status_code=204,
    summary="Revoke a folder grant (admin only)",
)
def remove_grant(
    user_id: str,
    path_prefix: str,
    auth: AuthContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    auth_service.revoke_grant(db, user_id, path_prefix)
