"""Service for managing documentation regeneration jobs."""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from ..models.generation_job import GenerationJob

logger = logging.getLogger(__name__)


class JobService:
    """
    Manages the lifecycle of documentation regeneration jobs.

    Jobs are created by webhooks, claimed by workers, and tracked
    through queued -> running -> completed/failed transitions.
    Duplicate webhooks for the same commit SHA are deduplicated.
    """

    def __init__(self, db: Session):
        self.db = db

    def enqueue(self, repo_url: str, commit_sha: Optional[str] = None) -> GenerationJob:
        """
        Create a new regeneration job, deduplicating by commit SHA.

        If a job already exists for this commit SHA (in any non-failed state),
        returns the existing job instead of creating a duplicate.

        Args:
            repo_url: Repository URL to regenerate docs for
            commit_sha: Git commit SHA that triggered the regeneration

        Returns:
            The created or existing GenerationJob
        """
        # Deduplicate: skip if a queued/running job exists for this commit
        if commit_sha:
            existing = (
                self.db.query(GenerationJob)
                .filter(
                    GenerationJob.repo_url == repo_url,
                    GenerationJob.commit_sha == commit_sha,
                    GenerationJob.status.in_(["queued", "running"])
                )
                .first()
            )
            if existing:
                logger.info(f"Job already exists for {repo_url} at {commit_sha[:8]}: {existing.id}")
                return existing

        job = GenerationJob(
            id=str(uuid.uuid4()),
            repo_url=repo_url,
            commit_sha=commit_sha,
            status="queued",
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        logger.info(f"Enqueued job {job.id} for {repo_url} (commit: {commit_sha[:8] if commit_sha else 'N/A'})")
        return job

    def claim_next(self) -> Optional[GenerationJob]:
        """
        Claim the oldest queued job for processing.

        Sets status to 'running' and records started_at timestamp.

        Returns:
            The claimed job, or None if no queued jobs exist
        """
        job = (
            self.db.query(GenerationJob)
            .filter(GenerationJob.status == "queued")
            .order_by(GenerationJob.created_at.asc())
            .first()
        )
        if not job:
            return None

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)

        logger.info(f"Claimed job {job.id} for {job.repo_url}")
        return job

    def complete(self, job_id: str) -> GenerationJob:
        """Mark a job as successfully completed."""
        job = self.db.query(GenerationJob).get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(job)

        logger.info(f"Job {job_id} completed successfully")
        return job

    def fail(self, job_id: str, error_message: str) -> GenerationJob:
        """
        Mark a job as failed.

        If retry_count < 1, re-queues the job for automatic retry.

        Args:
            job_id: The job to mark as failed
            error_message: Description of what went wrong
        """
        job = self.db.query(GenerationJob).get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        job.retry_count += 1

        if job.retry_count <= 1:
            # Re-queue for retry
            job.status = "queued"
            job.error_message = f"Retry after: {error_message}"
            logger.info(f"Job {job_id} failed, re-queuing (retry {job.retry_count})")
        else:
            # Exhausted retries
            job.status = "failed"
            job.error_message = error_message
            job.completed_at = datetime.now(timezone.utc)
            logger.warning(f"Job {job_id} failed permanently: {error_message}")

        self.db.commit()
        self.db.refresh(job)
        return job

    def get_jobs_for_repo(self, repo_url: str, limit: int = 10) -> List[GenerationJob]:
        """Get recent jobs for a repository, newest first."""
        return (
            self.db.query(GenerationJob)
            .filter(GenerationJob.repo_url == repo_url)
            .order_by(GenerationJob.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_job(self, job_id: str) -> Optional[GenerationJob]:
        """Get a specific job by ID."""
        return self.db.query(GenerationJob).get(job_id)

    def get_latest_for_repo(self, repo_url: str) -> Optional[GenerationJob]:
        """Get the most recent job for a repository."""
        return (
            self.db.query(GenerationJob)
            .filter(GenerationJob.repo_url == repo_url)
            .order_by(GenerationJob.created_at.desc())
            .first()
        )
