"""Folder metadata model for empty folders."""

from sqlalchemy import Column, String, Text, Integer, DateTime
from sqlalchemy.sql import func
from ..database import Base


class FolderMetadata(Base):
    """Table for storing metadata about folders, especially empty ones."""

    __tablename__ = "folder_metadata"

    # Primary key
    id = Column(String(50), primary_key=True)  # folder-{path_hash}

    # Folder location (full path including crate as first segment)
    path = Column(Text, nullable=False, unique=True)

    # Optional metadata
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)
    sort_order = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
