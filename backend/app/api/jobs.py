"""Generation job status endpoints."""

import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..database import get_db
from ..schemas.webhook import GenerationJobResponse
from ..services.job_service import JobService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=List[GenerationJobResponse])
def list_jobs(
    repo_url: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
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
    db: Session = Depends(get_db)
):
    """Get a specific generation job by ID."""
    service = JobService(db)
    job = service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job
