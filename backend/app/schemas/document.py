"""Document schemas."""

from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, List


class DocumentBase(BaseModel):
    """Base document schema."""
    repo_url: Optional[str] = None
    repo_name: Optional[str] = None
    path: str = ""  # Full path: "crate/folder/subfolder"
    title: str
    content: str
    doc_type: str = ""  # Legacy field
    keywords: List[str] = []  # User-editable classification tags

    @field_validator('path')
    @classmethod
    def normalize_path(cls, v: str) -> str:
        if not v:
            return ""
        v = v.strip().strip('/')
        while '//' in v:
            v = v.replace('//', '/')
        return v

    @field_validator('title')
    @classmethod
    def validate_title(cls, v: str) -> str:
        if '/' in v:
            raise ValueError("Title cannot contain '/' (use path field for folders)")
        return v.strip()


class DocumentCreate(DocumentBase):
    """Schema for creating a document."""
    author_type: str = "ai"
    author_metadata: Optional[dict] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "repo_url": "https://github.com/org/repo",
                    "repo_name": "repo",
                    "path": "repo/Architecture",
                    "title": "System Overview",
                    "content": "# System Overview\n\nThis document describes...",
                    "keywords": ["Technical Docs", "Architecture"],
                    "author_type": "ai",
                    "author_metadata": {"agent": "openhands", "model": "devstral"},
                }
            ]
        }
    }


class DocumentUpdate(BaseModel):
    """Schema for updating a document."""
    content: str
    author_type: str = "ai"
    author_metadata: Optional[dict] = None


class DocumentMoveRequest(BaseModel):
    """Schema for moving a document to a different path."""
    target_path: str


class DocumentKeywordsUpdate(BaseModel):
    """Schema for updating document keywords."""
    keywords: List[str]


class DocumentRepoUpdate(BaseModel):
    """Schema for updating document git repository URL."""
    repo_url: str


class SearchParams(BaseModel):
    """Parameters for full-text search with filters."""
    q: str
    path_prefix: Optional[str] = None
    keywords: Optional[List[str]] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = Field(20, ge=1, le=100)


class SearchResultResponse(BaseModel):
    """Search result with ranking and snippet."""
    id: str
    repo_name: Optional[str] = None
    path: str
    title: str
    doc_type: str = ""
    keywords: List[str] = []
    content_preview: Optional[str] = None
    updated_at: datetime
    generation_count: int
    rank: float = 0.0
    snippet: Optional[str] = None

    class Config:
        from_attributes = True


class BrokenLinkResponse(BaseModel):
    """Wikilink resolution status for a single link target."""
    target: str
    resolved: bool
    resolved_doc_id: Optional[str] = None


class BatchOperation(BaseModel):
    """Batch operation on multiple documents."""
    operation: str  # "move", "delete", "add_keywords", "remove_keywords"
    doc_ids: List[str]
    params: dict = {}


class BatchResult(BaseModel):
    """Result of a batch operation."""
    total: int
    succeeded: int
    failed: int
    errors: List[dict] = []


class DocumentResponse(DocumentBase):
    """Schema for document response."""
    id: str
    content_preview: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    generation_count: int
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Schema for document list response."""
    id: str
    repo_name: Optional[str] = None
    path: str
    title: str
    doc_type: str = ""
    keywords: List[str] = []
    content_preview: Optional[str] = None
    updated_at: datetime
    generation_count: int
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True
