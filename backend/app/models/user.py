"""User, FolderGrant, and AuditLog models.

Users authenticate with email/password and receive JWT tokens.
FolderGrants control which document subtrees a user can access.
AuditLog records all state-changing operations for accountability.
"""

from sqlalchemy import Column, String, DateTime, Boolean, Integer, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class User(Base):
    """User account with role-based access control.

    Roles (global default, can be overridden per-subtree via FolderGrant):
        admin  — full access to everything including user management
        editor — can read and edit documents within granted subtrees
        viewer — can only read documents within granted subtrees
    """

    __tablename__ = "users"

    user_id = Column(String(50), primary_key=True)
    display_name = Column(String(255), nullable=False, default="Default User")
    email = Column(String(255), unique=True, nullable=True)
    password_hash = Column(Text, nullable=True)
    role = Column(String(20), nullable=False, default="viewer")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    grants = relationship(
        "FolderGrant",
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="[FolderGrant.user_id]",
    )


class FolderGrant(Base):
    """Path-prefix grant controlling where a user can operate.

    A grant on path_prefix="backend-product-a" with role="editor" means the
    user can read and edit any document whose path starts with "backend-product-a/".

    An empty path_prefix ('') means root access — all documents.
    The most specific (longest) matching prefix wins when checking permissions.
    """

    __tablename__ = "folder_grants"

    user_id = Column(
        String(50),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    path_prefix = Column(String(500), primary_key=True, default="")
    role = Column(String(20), nullable=False, default="viewer")
    granted_by = Column(String(50), ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="grants", foreign_keys=[user_id])


class AuditLog(Base):
    """Immutable record of state-changing operations.

    Written by the service layer, never modified or deleted.
    Fields:
        action        — create, update, delete, restore, login, login_failed,
                        role_change, grant_create, grant_revoke
        resource_type — document, user, folder, grant
        resource_id   — ID of the affected resource
        details       — JSON string with additional context
    """

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), ForeignKey("users.user_id"), nullable=True)
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(255), nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
