"""Document API endpoints."""

from fastapi import APIRouter, Depends, Query, Body, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..core.auth import require_auth, optional_auth
from ..core.token_factory import TokenPayload
from ..database import get_db
from datetime import datetime
from ..schemas.document import DocumentCreate, DocumentResponse, DocumentListResponse, DocumentUpdate, DocumentMoveRequest, DocumentKeywordsUpdate, DocumentRepoUpdate, SearchResultResponse, BatchOperation, BatchResult
from ..services import DocumentService
from ..exceptions import DocumentNotFoundError

router = APIRouter(prefix="/api/docs", tags=["documents"])


@router.post("", response_model=DocumentResponse, status_code=201)
def create_document(
    document: DocumentCreate,
    db: Session = Depends(get_db),
    auth: TokenPayload = Depends(require_auth),
):
    """Create or update a document (upsert)."""
    service = DocumentService(db)
    return service.create_or_update_document(document)


@router.get("", response_model=List[DocumentListResponse])
def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    path_prefix: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """List all documents with pagination."""
    service = DocumentService(db)
    return service.list_documents(skip, limit, path_prefix)


# --- Fixed-path endpoints (must be before /{doc_id} to avoid route shadowing) ---


@router.get("/trash", response_model=List[DocumentListResponse])
def list_trash(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """List soft-deleted documents (trash). Returns empty list if trash is empty."""
    service = DocumentService(db)
    return service.list_trash(skip, limit)


@router.get("/search/", response_model=List[SearchResultResponse])
def search_documents(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    path_prefix: Optional[str] = None,
    keywords: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    """Full-text search with optional filters.

    `keywords` is a comma-separated string of keyword tags to filter by.
    """
    service = DocumentService(db)
    keyword_list = [k.strip() for k in keywords.split(',')] if keywords else None
    results = service.search_documents(
        q, limit, path_prefix, keyword_list, date_from, date_to
    )
    return [SearchResultResponse(**r) for r in results]


@router.get("/recent", response_model=List[DocumentListResponse])
def recent_documents(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get the most recently updated documents."""
    service = DocumentService(db)
    docs = service.get_recent_documents(limit)
    return [
        DocumentListResponse(
            id=doc.id,
            repo_name=doc.repo_name,
            doc_type=doc.doc_type,
            keywords=doc.keywords or [],
            path=doc.path,
            title=doc.title,
            content_preview=doc.content_preview,
            updated_at=doc.updated_at,
            generation_count=doc.generation_count,
        )
        for doc in docs
    ]


@router.post("/batch", response_model=BatchResult)
def batch_operation(
    batch: BatchOperation = Body(...),
    db: Session = Depends(get_db),
):
    """Execute a batch operation on multiple documents.

    Always returns 200 — partial failures are reported in the response body.
    Supported operations: move, delete, add_keywords, remove_keywords.
    """
    service = DocumentService(db)
    return service.execute_batch(batch.operation, batch.doc_ids, batch.params)


@router.get("/resolve/", response_model=dict)
def resolve_wikilink(
    target: str = Query(..., min_length=1),
    db: Session = Depends(get_db)
):
    """Resolve a wikilink target to a document ID."""
    service = DocumentService(db)
    doc_id = service.resolve_wikilink(target)
    if not doc_id:
        raise HTTPException(status_code=404, detail=f"Could not resolve wikilink: {target}")
    return {"target": target, "doc_id": doc_id}


# --- Parameterized endpoints (/{doc_id} and /{doc_id}/...) ---


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(
    doc_id: str,
    db: Session = Depends(get_db)
):
    """Get specific document by ID."""
    service = DocumentService(db)
    document = service.get_document(doc_id)
    if not document:
        raise DocumentNotFoundError(doc_id)
    return document


@router.put("/{doc_id}", response_model=DocumentResponse)
def update_document(
    doc_id: str,
    update_data: DocumentUpdate = Body(...),
    db: Session = Depends(get_db),
    auth: TokenPayload = Depends(require_auth),
):
    """Update document content (creates new version)."""
    service = DocumentService(db)
    return service.update_document(doc_id, update_data)


@router.put("/{doc_id}/move", response_model=DocumentResponse)
def move_document(
    doc_id: str,
    request: DocumentMoveRequest = Body(...),
    db: Session = Depends(get_db),
    auth: TokenPayload = Depends(require_auth),
):
    """Move a document to a different folder path."""
    service = DocumentService(db)
    try:
        return service.move_document(doc_id, request.target_path)
    except DocumentNotFoundError:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{doc_id}/keywords", response_model=DocumentResponse)
def update_keywords(
    doc_id: str,
    request: DocumentKeywordsUpdate = Body(...),
    db: Session = Depends(get_db),
    auth: TokenPayload = Depends(require_auth),
):
    """Update a document's keywords."""
    service = DocumentService(db)
    return service.update_keywords(doc_id, request.keywords)


@router.put("/{doc_id}/repo", response_model=DocumentResponse)
def update_repo_url(
    doc_id: str,
    request: DocumentRepoUpdate = Body(...),
    db: Session = Depends(get_db),
    auth: TokenPayload = Depends(require_auth),
):
    """Update a document's git repository URL."""
    service = DocumentService(db)
    return service.update_repo_url(doc_id, request.repo_url)


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    auth: TokenPayload = Depends(require_auth),
):
    """Soft-delete a document (moves to trash). Idempotent."""
    service = DocumentService(db)
    service.delete_document(doc_id)
    return None


@router.post("/{doc_id}/restore", response_model=DocumentResponse)
def restore_document(
    doc_id: str,
    db: Session = Depends(get_db),
    auth: TokenPayload = Depends(require_auth),
):
    """Restore a soft-deleted document. Idempotent — returns the doc even if not deleted."""
    service = DocumentService(db)
    doc = service.restore_document(doc_id)
    if not doc:
        raise DocumentNotFoundError(doc_id)
    return doc


@router.delete("/{doc_id}/permanent", status_code=204)
def permanent_delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    auth: TokenPayload = Depends(require_auth),
):
    """Permanently delete a document and all versions. Idempotent."""
    service = DocumentService(db)
    service.permanent_delete_document(doc_id)
    return None


@router.get("/{doc_id}/broken-links", response_model=list)
def get_broken_links(
    doc_id: str,
    db: Session = Depends(get_db),
):
    """Check all wikilinks in a document and report which ones are broken.

    Returns an empty list if the document has no wikilinks — not an error.
    """
    service = DocumentService(db)
    return service.dep_service.get_broken_links(doc_id)
