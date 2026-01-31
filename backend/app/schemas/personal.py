"""Schemas for personal tree API."""

from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional, List


# --- Folder schemas ---

class PersonalFolderCreate(BaseModel):
    """Create a personal folder."""
    user_id: str = "default"
    name: str
    parent_id: Optional[str] = None

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Folder name cannot be empty")
        if '/' in v:
            raise ValueError("Folder name cannot contain '/'")
        return v


class PersonalFolderResponse(BaseModel):
    """Personal folder in API responses."""
    folder_id: str
    user_id: str
    name: str
    parent_id: Optional[str] = None
    sort_order: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class PersonalFolderMove(BaseModel):
    """Move a personal folder to a new parent."""
    parent_id: Optional[str] = None  # None = root level


# --- Document ref schemas ---

class PersonalDocRefCreate(BaseModel):
    """Add a document reference to a personal folder."""
    user_id: str = "default"
    document_id: str


class PersonalDocRefResponse(BaseModel):
    """Document reference in API responses."""
    ref_id: str
    user_id: str
    folder_id: str
    document_id: str
    sort_order: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


# --- Tree schema ---

class PersonalTreeNode(BaseModel):
    """A node in the personal tree (folder or document reference)."""
    id: str
    name: str
    type: str  # 'folder' or 'document'
    folder_id: Optional[str] = None  # For folders: their own ID
    document_id: Optional[str] = None  # For doc refs: the org document ID
    ref_id: Optional[str] = None  # For doc refs: the reference ID
    children: List['PersonalTreeNode'] = []
