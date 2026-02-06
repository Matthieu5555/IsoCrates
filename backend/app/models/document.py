"""Document model."""

from sqlalchemy import Column, Index, String, Text, Integer, DateTime, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Document(Base):
    """Main documents table."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_path", "path"),
        Index("ix_documents_updated_at", "updated_at"),
        Index("ix_documents_repo_url", "repo_url"),
    )

    # Primary key
    id = Column(String(50), primary_key=True)  # doc-{hash}-{type}

    # Repository info (nullable to support standalone documents)
    repo_url = Column(Text, nullable=True)
    repo_name = Column(String(255), nullable=True)

    # Hierarchical structure
    # path holds the full location: "crate/folder/subfolder"
    # First segment = crate (top-level project), rest = folder hierarchy
    path = Column(String(500), default='')
    title = Column(String(255), nullable=False)  # Document title: "Async Patterns"

    # Legacy field (kept for backward compatibility, can be derived from path)
    doc_type = Column(String(100), default='')

    # User-editable classification tags (e.g. ["Client Facing", "Technical Docs"])
    keywords = Column(JSON, default=list)

    # Content
    content = Column(Text, nullable=False)
    content_preview = Column(Text)  # First 500 chars for quick display

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Generation tracking
    generation_count = Column(Integer, default=1)

    # Optimistic locking — incremented on every content update.
    # Clients must send their known version; mismatches yield HTTP 409.
    version = Column(Integer, default=1, nullable=False)

    # Soft delete (NULL = active, timestamp = deleted)
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)

    # Relationships
    versions = relationship("Version", back_populates="document", cascade="all, delete-orphan")
    dependencies_from = relationship(
        "Dependency",
        foreign_keys="Dependency.from_doc_id",
        back_populates="from_document",
        cascade="all, delete-orphan"
    )
    dependencies_to = relationship(
        "Dependency",
        foreign_keys="Dependency.to_doc_id",
        back_populates="to_document",
        cascade="all, delete-orphan"
    )

    @property
    def source_type(self) -> str:
        """Return 'repository' if linked to a repo, 'standalone' otherwise."""
        return 'repository' if self.repo_url else 'standalone'
