"""Folder and tree schemas."""

from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional, List, Dict, Any


class FolderMetadataBase(BaseModel):
    """Base folder metadata schema."""
    path: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int = 0

    @field_validator('path')
    @classmethod
    def validate_path(cls, v: str) -> str:
        """Validate and normalize path."""
        v = v.strip().strip('/')
        if not v:
            raise ValueError("Path cannot be empty")
        while '//' in v:
            v = v.replace('//', '/')
        return v


class FolderMetadataCreate(FolderMetadataBase):
    """Schema for creating folder metadata."""
    pass


class FolderMetadataUpdate(BaseModel):
    """Schema for updating folder metadata."""
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: Optional[int] = None


class FolderMetadataResponse(FolderMetadataBase):
    """Schema for folder metadata response."""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FolderMoveRequest(BaseModel):
    """Request to move a folder to a new location."""
    source_path: str
    target_path: str


class FolderOperationResponse(BaseModel):
    """Response for folder mutation operations (move, delete)."""
    affected_documents: int
    folder_path: str
    old_path: Optional[str] = None
    new_path: Optional[str] = None
    tree: List[Dict[str, Any]]


class TreeNode(BaseModel):
    """Schema for tree navigation."""
    id: str
    name: str
    type: str  # 'document' or 'folder'
    is_crate: bool = False  # True for top-level folders
    doc_type: Optional[str] = None
    path: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    children: List['TreeNode'] = []

    class Config:
        from_attributes = True
