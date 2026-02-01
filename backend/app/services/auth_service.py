"""Authentication service — user CRUD, password hashing, grant management.

All password operations use bcrypt via passlib. Passwords are never stored
or logged in plaintext. The service layer owns user lifecycle; endpoints
are thin wrappers.
"""

import logging
import uuid
from typing import Optional

from passlib.hash import bcrypt
from sqlalchemy.orm import Session

from ..exceptions import ValidationError, AuthenticationError
from ..models.user import User, FolderGrant

logger = logging.getLogger(__name__)


def register_user(
    db: Session,
    email: str,
    password: str,
    display_name: str,
    role: str = "viewer",
) -> User:
    """Create a new user account.

    The first user registered is automatically promoted to admin with a root
    grant. Subsequent users default to viewer with no grants (an admin must
    assign grants explicitly).

    Raises ValidationError if email is already taken or inputs are invalid.
    """
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValidationError("Valid email address required", field="email")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters", field="password")
    if not display_name.strip():
        raise ValidationError("Display name required", field="display_name")

    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        raise ValidationError("Email already registered", field="email")

    # First user becomes admin
    user_count = db.query(User).filter(User.email.isnot(None)).count()
    is_first_user = user_count == 0
    effective_role = "admin" if is_first_user else role

    user_id = str(uuid.uuid4())[:8]
    user = User(
        user_id=user_id,
        display_name=display_name.strip(),
        email=email,
        password_hash=bcrypt.hash(password),
        role=effective_role,
        is_active=True,
    )
    db.add(user)

    # First user gets root grant (access to everything)
    if is_first_user:
        root_grant = FolderGrant(
            user_id=user_id,
            path_prefix="",
            role="admin",
        )
        db.add(root_grant)
        logger.info("First user registered as admin with root grant: %s", email)

    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    """Validate credentials and return the user.

    Raises AuthenticationError on invalid email, wrong password, or inactive account.
    """
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()

    if user is None or user.password_hash is None:
        raise AuthenticationError("Invalid email or password")

    if not bcrypt.verify(password, user.password_hash):
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        raise AuthenticationError("Account is deactivated")

    return user


def get_user_by_id(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.user_id == user_id).first()


def list_users(db: Session) -> list[User]:
    """List all users with email accounts (excludes legacy default user)."""
    return db.query(User).filter(User.email.isnot(None)).order_by(User.created_at).all()


def update_user_role(db: Session, user_id: str, new_role: str) -> User:
    """Change a user's global role."""
    if new_role not in ("admin", "editor", "viewer"):
        raise ValidationError(f"Invalid role: {new_role}. Must be admin, editor, or viewer.", field="role")

    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise ValidationError("User not found", field="user_id")

    user.role = new_role
    db.commit()
    db.refresh(user)
    return user


def deactivate_user(db: Session, user_id: str) -> User:
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise ValidationError("User not found", field="user_id")
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


def get_user_grants(db: Session, user_id: str) -> list[FolderGrant]:
    return db.query(FolderGrant).filter(FolderGrant.user_id == user_id).all()


def create_grant(
    db: Session,
    user_id: str,
    path_prefix: str,
    role: str,
    granted_by: Optional[str] = None,
) -> FolderGrant:
    """Add a folder grant for a user.

    If a grant already exists for the same (user_id, path_prefix), it is
    updated with the new role.
    """
    if role not in ("admin", "editor", "viewer"):
        raise ValidationError(f"Invalid role: {role}", field="role")

    path_prefix = path_prefix.strip("/")

    existing = (
        db.query(FolderGrant)
        .filter(FolderGrant.user_id == user_id, FolderGrant.path_prefix == path_prefix)
        .first()
    )
    if existing is not None:
        existing.role = role
        existing.granted_by = granted_by
        db.commit()
        db.refresh(existing)
        return existing

    grant = FolderGrant(
        user_id=user_id,
        path_prefix=path_prefix,
        role=role,
        granted_by=granted_by,
    )
    db.add(grant)
    db.commit()
    db.refresh(grant)
    return grant


def revoke_grant(db: Session, user_id: str, path_prefix: str) -> bool:
    """Remove a folder grant. Returns True if a grant was removed."""
    path_prefix = path_prefix.strip("/")
    grant = (
        db.query(FolderGrant)
        .filter(FolderGrant.user_id == user_id, FolderGrant.path_prefix == path_prefix)
        .first()
    )
    if grant is None:
        return False
    db.delete(grant)
    db.commit()
    return True
