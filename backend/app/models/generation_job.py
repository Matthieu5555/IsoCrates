"""Generation job model for tracking webhook-triggered documentation regeneration."""

from sqlalchemy import Column, String, Text, Integer, DateTime
from sqlalchemy.sql import func
from ..database import Base


class GenerationJob(Base):
    """
    Tracks documentation regeneration jobs triggered by webhooks.

    Status transitions: queued -> running -> completed | failed
    Failed jobs with retry_count < 1 are eligible for automatic retry.
    """

    __tablename__ = "generation_jobs"

    # Primary key (UUID format)
    id = Column(String(50), primary_key=True)

    # Repository being regenerated
    repo_url = Column(Text, nullable=False)

    # Commit SHA that triggered regeneration (used for deduplication)
    commit_sha = Column(String(40), nullable=True)

    # Job lifecycle
    # Allowed values: queued, running, completed, failed
    status = Column(String(20), nullable=False, default="queued")
    error_message = Column(Text, nullable=True)

    # Failed jobs are retried once automatically
    retry_count = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
