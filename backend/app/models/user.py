"""User model."""

from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from ..database import Base


class User(Base):
    """User table — default user for now, future auth-ready."""

    __tablename__ = "users"

    user_id = Column(String(50), primary_key=True, default="default")
    display_name = Column(String(255), nullable=False, default="Default User")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
