"""Version API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List

from ..core.auth import AuthContext, optional_auth
from ..database import get_db
from ..schemas.version import VersionResponse
from ..services import DocumentService

router = APIRouter(prefix="/api/docs/{doc_id}/versions", tags=["versions"])


@router.get("", response_model=List[VersionResponse])
def list_versions(
    doc_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(optional_auth),
):
    """List all versions for a document."""
    service = DocumentService(db)
    service.get_document_authorized(doc_id, auth.grants, "read")
    return service.get_document_versions(doc_id, skip, limit)


@router.get("/latest", response_model=VersionResponse)
def get_latest_version(
    doc_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(optional_auth),
):
    """Get latest version for a document."""
    service = DocumentService(db)
    service.get_document_authorized(doc_id, auth.grants, "read")
    version = service.get_latest_version(doc_id)
    if not version:
        raise HTTPException(status_code=404, detail="No versions found")
    return version


@router.get("/{version_id}", response_model=VersionResponse)
def get_version(
    doc_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(optional_auth),
):
    """Get specific version."""
    service = DocumentService(db)
    service.get_document_authorized(doc_id, auth.grants, "read")
    version = service.get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    if version.doc_id != doc_id:
        raise HTTPException(status_code=404, detail="Version not found for this document")
    return version
