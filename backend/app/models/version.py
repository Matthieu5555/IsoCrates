"""Version model."""

from sqlalchemy import Column, Index, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Version(Base):
    """Version history table."""

    __tablename__ = "versions"
    __table_args__ = (
        Index("ix_versions_doc_id", "doc_id"),
        Index("ix_versions_created_at", "created_at"),
    )

    # Primary key
    version_id = Column(String(100), primary_key=True)  # {doc_id}-{timestamp}

    # Foreign key to document
    doc_id = Column(String(50), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Content
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False)  # SHA256 for deduplication

    # Author info
    author_type = Column(String(10), nullable=False)  # 'ai' or 'human'
    author_metadata = Column(JSON)  # {agent, model, trigger, etc.}

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    document = relationship("Document", back_populates="versions")
