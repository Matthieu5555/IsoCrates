"""Dependency schemas."""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class DependencyBase(BaseModel):
    """Base dependency schema."""
    from_doc_id: str
    to_doc_id: str
    link_type: str = "wikilink"
    link_text: Optional[str] = None
    section: Optional[str] = None


class DependencyCreate(DependencyBase):
    """Schema for creating a dependency."""
    pass


class DependencyResponse(DependencyBase):
    """Schema for dependency response."""
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
