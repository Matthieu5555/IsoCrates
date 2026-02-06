"""Webhook and generation job schemas."""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class WebhookResponse(BaseModel):
    """Response after receiving a webhook."""
    status: str
    job_id: Optional[str] = None
    message: str


class ManualJobRequest(BaseModel):
    """Request to manually trigger documentation generation."""
    repo_url: str


class GenerationJobResponse(BaseModel):
    """Schema for generation job status."""
    id: str
    repo_url: str
    commit_sha: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    retry_count: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True
