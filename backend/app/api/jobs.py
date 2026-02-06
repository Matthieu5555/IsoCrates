"""Generation job status endpoints."""

import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..core.auth import AuthContext, require_auth, optional_auth
from ..schemas.webhook import GenerationJobResponse, ManualJobRequest
from ..services.job_service import JobService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=GenerationJobResponse, status_code=201)
def create_job(
    request: ManualJobRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Manually trigger documentation generation for a repository.

    Creates a queued generation job. The worker will pick it up and
    run the agent pipeline. The agent's version priority engine
    handles the "nothing changed" case cheaply.
    """
    service = JobService(db)
    job = service.enqueue(repo_url=request.repo_url, commit_sha=None)
    logger.info(f"Manual generation triggered for {request.repo_url} by user {auth.user_id}")
    return job


@router.get("", response_model=List[GenerationJobResponse])
def list_jobs(
    repo_url: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(optional_auth),
):
    """List generation jobs, optionally filtered by repository URL."""
    service = JobService(db)

    if repo_url:
        return service.get_jobs_for_repo(repo_url, limit)

    # No filter — return recent jobs across all repos
    from ..models.generation_job import GenerationJob
    return (
        db.query(GenerationJob)
        .order_by(GenerationJob.created_at.desc())
        .limit(limit)
        .all()
    )


@router.get("/{job_id}", response_model=GenerationJobResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(optional_auth),
):
    """Get a specific generation job by ID."""
    service = JobService(db)
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job
