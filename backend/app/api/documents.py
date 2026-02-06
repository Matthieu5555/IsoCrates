"""Document API endpoints with path-based permission checks.

Endpoints are thin — DocumentService handles the full lifecycle
(CRUD, versioning, wikilink dependencies) as a deep module.
"""

from fastapi import APIRouter, Depends, Query, Body, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional

from ..core.auth import AuthContext, require_auth, require_admin, optional_auth
from ..database import get_db
from datetime import datetime
from ..schemas.document import DocumentCreate, DocumentResponse, DocumentListResponse, DocumentUpdate, DocumentMoveRequest, DocumentKeywordsUpdate, DocumentRepoUpdate, SearchResultResponse, BatchOperation, BatchResult, GenerateIdRequest, GenerateIdResponse
from ..services import DocumentService
from ..services.dependency_service import DependencyService
from ..services.permission_service import check_permission, filter_paths_by_grants
from ..exceptions import DocumentNotFoundError, ForbiddenError

router = APIRouter(prefix="/api/docs", tags=["documents"])


def _prefixes_from_auth(auth: Optional[AuthContext]) -> Optional[list[str]]:
    """Extract allowed path prefixes from auth context for SQL-level filtering.

    Returns None when no filtering is needed (no auth / auth disabled).
    """
    if auth is None:
        return None
    return filter_paths_by_grants(auth.grants)


def _check_doc_access(service: DocumentService, auth: Optional[AuthContext], doc_id: str, action: str):
    """Load a document and verify the user has permission. Returns the document.

    Returns 404 (not 403) when access is denied — the document is invisible,
    not forbidden. This prevents information leakage about document existence.
    """
    doc = service.get_document(doc_id)
    if doc is None:
        raise DocumentNotFoundError(doc_id)
    if auth is not None and not check_permission(auth.grants, doc.path, action):
        # Return 404 to avoid leaking that the document exists
        raise DocumentNotFoundError(doc_id)
    return doc


@router.post("", response_model=DocumentResponse, status_code=201)
def create_document(
    document: DocumentCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Create or update a document (upsert)."""
    if not check_permission(auth.grants, document.path, "edit"):
        raise ForbiddenError("No edit access to this path")

    service = DocumentService(db)
    doc, _is_new = service.create_or_update_document(document)
    return doc


@router.get("", response_model=List[DocumentListResponse])
def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    path_prefix: Optional[str] = None,
    repo_url: Optional[str] = None,
    db: Session = Depends(get_db),
    auth: Optional[AuthContext] = Depends(optional_auth),
):
    """List documents filtered by the user's folder grants."""
    service = DocumentService(db)
    return service.list_documents(
        skip, limit, path_prefix, repo_url=repo_url,
        allowed_prefixes=_prefixes_from_auth(auth),
    )


# --- Fixed-path endpoints (must be before /{doc_id} to avoid route shadowing) ---


@router.get("/trash", response_model=List[DocumentListResponse])
def list_trash(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """List soft-deleted documents (trash). Filtered by grants."""
    service = DocumentService(db)
    return service.list_trash(skip, limit, allowed_prefixes=_prefixes_from_auth(auth))


@router.get("/search/", response_model=List[SearchResultResponse])
def search_documents(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, ge=1, le=100),
    path_prefix: Optional[str] = None,
    keywords: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    db: Session = Depends(get_db),
    auth: Optional[AuthContext] = Depends(optional_auth),
):
    """Full-text search with optional filters, scoped to user's grants."""
    service = DocumentService(db)
    keyword_list = [k.strip() for k in keywords.split(',')] if keywords else None
    return service.search_documents(
        q, limit, path_prefix, keyword_list, date_from, date_to,
        allowed_prefixes=_prefixes_from_auth(auth),
    )


@router.get("/recent", response_model=List[DocumentListResponse])
def recent_documents(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    auth: Optional[AuthContext] = Depends(optional_auth),
):
    """Get the most recently updated documents, scoped to user's grants."""
    service = DocumentService(db)
    docs = service.get_recent_documents(limit, allowed_prefixes=_prefixes_from_auth(auth))

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
    auth: AuthContext = Depends(require_auth),
):
    """Execute a batch operation on multiple documents with permission filtering."""
    service = DocumentService(db)
    return service.execute_batch_authorized(
        operation=batch.operation,
        doc_ids=batch.doc_ids,
        params=batch.params,
        grants=auth.grants,
        is_service_account=auth.is_service_account,
    )


@router.post("/generate-id", response_model=GenerateIdResponse)
def generate_id(
    request: GenerateIdRequest,
    db: Session = Depends(get_db),
):
    """Generate a stable document ID from repo URL, path, and title.

    Pure function — no side effects, no auth required. This is the single
    source of truth for document ID generation, eliminating the need for
    duplicate implementations in the agent or other clients.
    """
    service = DocumentService(db)
    doc_id = service.generate_doc_id(
        repo_url=request.repo_url,
        path=request.path,
        title=request.title,
        doc_type=request.doc_type,
    )
    return GenerateIdResponse(doc_id=doc_id)


@router.post("/batch-titles", response_model=dict)
def batch_titles(
    doc_ids: List[str] = Body(..., embed=True),
    db: Session = Depends(get_db),
    auth: Optional[AuthContext] = Depends(optional_auth),
):
    """Resolve a list of document IDs to their titles. Returns {id: title} map.

    Capped at 100 IDs per request. Respects permission grants — documents
    the caller cannot read are silently omitted from results.
    """
    service = DocumentService(db)
    result = {}
    for doc_id in doc_ids[:100]:
        doc = service.get_document(doc_id)
        if doc is not None:
            if auth is None or check_permission(auth.grants, doc.path, "read"):
                result[doc_id] = doc.title
    return result


@router.get("/resolve/", response_model=dict)
def resolve_wikilink(
    target: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    auth: Optional[AuthContext] = Depends(optional_auth),
):
    """Resolve a wikilink target to a document ID (respects permission grants)."""
    dep_service = DependencyService(db)
    doc_id = dep_service.resolve_wikilink(target)
    if not doc_id:
        raise HTTPException(status_code=404, detail=f"Could not resolve wikilink: {target}")

    # When auth is active, verify caller can see the resolved document
    if auth is not None:
        service = DocumentService(db)
        doc = service.get_document(doc_id)
        if doc is None or not check_permission(auth.grants, doc.path, "read"):
            raise HTTPException(status_code=404, detail=f"Could not resolve wikilink: {target}")

    return {"target": target, "doc_id": doc_id}


# --- Parameterized endpoints (/{doc_id} and /{doc_id}/...) ---


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(
    doc_id: str,
    db: Session = Depends(get_db),
    auth: Optional[AuthContext] = Depends(optional_auth),
):
    """Get specific document by ID. Returns 404 if not found or no access."""
    service = DocumentService(db)
    doc = _check_doc_access(service, auth, doc_id, "read")
    return doc


@router.put("/{doc_id}", response_model=DocumentResponse)
def update_document(
    doc_id: str,
    update_data: DocumentUpdate = Body(...),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Update document content (creates new version)."""
    service = DocumentService(db)
    _check_doc_access(service, auth, doc_id, "edit")
    return service.update_document(doc_id, update_data)


@router.put("/{doc_id}/move", response_model=DocumentResponse)
def move_document(
    doc_id: str,
    request: DocumentMoveRequest = Body(...),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Move a document to a different folder path. Requires edit on both source and target."""
    service = DocumentService(db)
    _check_doc_access(service, auth, doc_id, "edit")

    if not check_permission(auth.grants, request.target_path, "edit"):
        raise ForbiddenError("No edit access to target path")

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
    auth: AuthContext = Depends(require_auth),
):
    """Update a document's keywords."""
    service = DocumentService(db)
    _check_doc_access(service, auth, doc_id, "edit")
    return service.update_keywords(doc_id, request.keywords)


@router.put("/{doc_id}/repo", response_model=DocumentResponse)
def update_repo_url(
    doc_id: str,
    request: DocumentRepoUpdate = Body(...),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Update a document's git repository URL."""
    service = DocumentService(db)
    _check_doc_access(service, auth, doc_id, "edit")
    return service.update_repo_url(doc_id, request.repo_url)


@router.delete("/{doc_id}", status_code=204)
def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Soft-delete a document (moves to trash). Idempotent — succeeds if already deleted."""
    service = DocumentService(db)
    doc = service.get_document(doc_id)
    if doc is not None and not check_permission(auth.grants, doc.path, "delete"):
        raise DocumentNotFoundError(doc_id)
    # Idempotent: if doc is None (already deleted or never existed), still succeeds
    service.delete_document(doc_id)
    return None


@router.post("/{doc_id}/restore", response_model=DocumentResponse)
def restore_document(
    doc_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Restore a soft-deleted document. Requires edit permission on the doc's path."""
    from ..repositories.document_repository import DocumentRepository
    doc_repo = DocumentRepository(db)
    doc = doc_repo.get_by_id_including_deleted(doc_id)
    if doc is None:
        raise DocumentNotFoundError(doc_id)
    if not check_permission(auth.grants, doc.path or "", "edit"):
        raise DocumentNotFoundError(doc_id)  # 404 to avoid leaking existence
    service = DocumentService(db)
    return service.restore_document(doc_id)


@router.delete("/{doc_id}/permanent", status_code=204)
def permanent_delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_admin),
):
    """Permanently delete a document and all versions. Admin only. Idempotent."""
    service = DocumentService(db)
    service.permanent_delete_document(doc_id)
    return None


@router.get("/{doc_id}/broken-links", response_model=list)
def get_broken_links(
    doc_id: str,
    db: Session = Depends(get_db),
    auth: Optional[AuthContext] = Depends(optional_auth),
):
    """Check all wikilinks in a document and report which ones are broken."""
    doc_service = DocumentService(db)
    dep_service = DependencyService(db)

    _check_doc_access(doc_service, auth, doc_id, "read")
    return dep_service.get_broken_links(doc_id)
