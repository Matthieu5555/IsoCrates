"""Dependency API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from ..core.auth import AuthContext, require_auth, require_admin, optional_auth
from ..database import get_db
from ..exceptions import DocumentNotFoundError
from ..schemas.dependency import DependencyCreate, DependencyResponse, DocumentDependencies
from ..services.dependency_service import DependencyService
from ..services.permission_service import check_permission

router = APIRouter(prefix="/api/docs/{doc_id}/dependencies", tags=["dependencies"])


@router.get("", response_model=DocumentDependencies)
def get_dependencies(
    doc_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(optional_auth),
):
    """Get all dependencies for a document (incoming and outgoing)."""
    from ..services import DocumentService

    service = DocumentService(db)
    service.get_document_authorized(doc_id, auth.grants, "read")

    dep_service = DependencyService(db)
    return dep_service.get_dependencies(doc_id)


@router.post("", response_model=DependencyResponse, status_code=201)
def create_dependency(
    doc_id: str,
    dependency: DependencyCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Create a new dependency link."""
    from ..exceptions import ValidationError

    if dependency.from_doc_id != doc_id:
        raise ValidationError("from_doc_id must match doc_id in path", field="from_doc_id")

    service = DependencyService(db)
    result = service.create_dependency(dependency)
    db.commit()
    return result


# Add a global endpoint for getting all dependencies (for graph view)
graph_router = APIRouter(prefix="/api/dependencies", tags=["dependencies"])


@graph_router.get("", response_model=List[DependencyResponse])
def get_all_dependencies(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(optional_auth),
):
    """Get all dependencies across all documents (for graph visualization).

    Filters to only include dependencies where both documents are accessible
    to the current user. Permission filtering is pushed into SQL to avoid
    loading all documents into memory.
    """
    from ..services.permission_service import filter_paths_by_grants

    dep_service = DependencyService(db)
    allowed_prefixes = filter_paths_by_grants(auth.grants)
    return dep_service.get_all_dependencies(allowed_prefixes=allowed_prefixes)


@graph_router.post("/reindex")
def reindex_dependencies(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    """Reindex all document dependencies from wikilinks. Admin only."""
    from ..repositories.document_repository import DocumentRepository

    service = DependencyService(db)
    doc_repo = DocumentRepository(db)

    docs = doc_repo.get_all(skip=0, limit=10000)
    processed = 0
    for doc in docs:
        service.replace_document_dependencies(doc.id, doc.content)
        processed += 1

    db.commit()
    deps = service.get_all_dependencies()
    return {"documents_processed": processed, "dependencies_created": len(deps)}
