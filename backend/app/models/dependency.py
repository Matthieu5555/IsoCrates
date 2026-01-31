"""Dependency model."""

from sqlalchemy import Column, Index, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Dependency(Base):
    """Document dependency/links table."""

    __tablename__ = "dependencies"
    __table_args__ = (
        Index("ix_dependencies_from_doc_id", "from_doc_id"),
        Index("ix_dependencies_to_doc_id", "to_doc_id"),
        Index("ix_dependencies_pair", "from_doc_id", "to_doc_id", unique=True),
    )

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    from_doc_id = Column(String(50), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    to_doc_id = Column(String(50), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Link info
    link_type = Column(String(50), default='wikilink')
    link_text = Column(Text)
    section = Column(String(255))

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    from_document = relationship("Document", foreign_keys=[from_doc_id], back_populates="dependencies_from")
    to_document = relationship("Document", foreign_keys=[to_doc_id], back_populates="dependencies_to")
