"""Version schemas."""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class VersionBase(BaseModel):
    """Base version schema."""
    content: str
    author_type: str  # 'ai' or 'human'
    author_metadata: Optional[dict] = None


class VersionCreate(VersionBase):
    """Schema for creating a version."""
    doc_id: str


class VersionResponse(VersionBase):
    """Schema for version response."""
    version_id: str
    doc_id: str
    content_hash: str
    created_at: datetime

    class Config:
        from_attributes = True
