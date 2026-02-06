"""Audit logging service — records all state-changing operations.

Entries are immutable. The service provides a write-only interface for the
application and a read interface for admins.

Usage in service layer:
    audit_service.log(db, user_id="abc", action="update", resource_type="document",
                      resource_id="doc-123", details={"field": "content"})
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy.exc
from sqlalchemy.orm import Session

from ..models.user import AuditLog

logger = logging.getLogger(__name__)


def log(
    db: Session,
    user_id: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Write an audit log entry. Never raises — audit failures are logged but don't break operations."""
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=json.dumps(details) if details else None,
            ip_address=ip_address,
        )
        db.add(entry)
        db.commit()
    except sqlalchemy.exc.SQLAlchemyError as e:
        logger.warning("Failed to write audit log: %s", e)
        db.rollback()


def get_recent(db: Session, limit: int = 100) -> list[AuditLog]:
    """Get the most recent audit log entries."""
    return (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )


def get_by_user(db: Session, user_id: str, limit: int = 100) -> list[AuditLog]:
    """Get audit log entries for a specific user."""
    return (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )


def get_by_resource(db: Session, resource_type: str, resource_id: str, limit: int = 100) -> list[AuditLog]:
    """Get audit log entries for a specific resource."""
    return (
        db.query(AuditLog)
        .filter(AuditLog.resource_type == resource_type, AuditLog.resource_id == resource_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )


def purge_old_entries(db: Session, days: int = 365) -> int:
    """Delete audit log entries older than `days`. Returns count of deleted rows.

    Skipped when days <= 0 (keep forever). Never raises — logs failures.
    """
    if days <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        count = db.query(AuditLog).filter(AuditLog.created_at < cutoff).delete()
        db.commit()
        return count
    except sqlalchemy.exc.SQLAlchemyError as e:
        logger.warning("Failed to purge audit log: %s", e)
        db.rollback()
        return 0
