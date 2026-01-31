"""Personal tree models — per-user folder structure with document references."""

from sqlalchemy import Column, Index, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.sql import func
from ..database import Base


class PersonalFolder(Base):
    """A folder in a user's personal tree."""

    __tablename__ = "personal_folders"
    __table_args__ = (
        Index("ix_personal_folders_user_id", "user_id"),
        Index("ix_personal_folders_parent_id", "parent_id"),
    )

    folder_id = Column(String(50), primary_key=True)
    user_id = Column(String(50), ForeignKey("users.user_id"), nullable=False)
    name = Column(String(255), nullable=False)
    parent_id = Column(String(50), ForeignKey("personal_folders.folder_id", ondelete="CASCADE"), nullable=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PersonalDocumentRef(Base):
    """A reference from a personal folder to an org document (not a copy)."""

    __tablename__ = "personal_document_refs"
    __table_args__ = (
        Index("ix_personal_refs_user_folder", "user_id", "folder_id"),
        Index("ix_personal_refs_document_id", "document_id"),
    )

    ref_id = Column(String(50), primary_key=True)
    user_id = Column(String(50), ForeignKey("users.user_id"), nullable=False)
    folder_id = Column(String(50), ForeignKey("personal_folders.folder_id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(50), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
