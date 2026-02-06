"""Dependency API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, List

from ..core.auth import require_auth, AuthContext
from ..core.token_factory import TokenPayload
from ..database import get_db
from ..schemas.dependency import DependencyCreate, DependencyResponse, DocumentDependencies
from ..services.dependency_service import DependencyService

router = APIRouter(prefix="/api/docs/{doc_id}/dependencies", tags=["dependencies"])


@router.get("", response_model=DocumentDependencies)
def get_dependencies(
    doc_id: str,
    db: Session = Depends(get_db)
):
    """Get all dependencies for a document (incoming and outgoing)."""
    service = DependencyService(db)
    return service.get_dependencies(doc_id)


@router.post("", response_model=DependencyResponse, status_code=201)
def create_dependency(
    doc_id: str,
    dependency: DependencyCreate,
    db: Session = Depends(get_db),
    auth: TokenPayload = Depends(require_auth),
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
def get_all_dependencies(db: Session = Depends(get_db)):
    """Get all dependencies across all documents (for graph visualization)."""
    service = DependencyService(db)
    return service.get_all_dependencies()


@graph_router.post("/reindex")
def reindex_dependencies(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Reindex all document dependencies from wikilinks.

    Processes all documents and extracts wikilinks to populate the dependencies table.
    Useful when documents were created before their wikilink targets existed.
    """
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
