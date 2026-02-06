"""Document service — deep module for document lifecycle.

Owns the full lifecycle of document operations: CRUD, versioning, and
wikilink dependency management. Callers interact with a single service
through high-level operations; internal coordination with DependencyService
is hidden behind the interface.
"""

from sqlalchemy.orm import Session
from typing import List, Optional
import hashlib
import logging
from ..models import Document
from ..schemas.document import DocumentCreate, DocumentUpdate, DocumentListResponse, DocumentKeywordsUpdate, SearchResultResponse, BatchResult, BatchError
from ..repositories import DocumentRepository, VersionRepository
from ..schemas.version import VersionCreate
from ..exceptions import DocumentNotFoundError, ConflictError, ValidationError
from ..services.dependency_service import DependencyService

# Number of hex chars used from SHA-256 hash for document ID components.
# 12 hex chars = 48 bits → ~281 trillion possible values per component.
# Collision probability stays negligible up to millions of documents.
DOC_ID_REPO_HASH_LENGTH = 12
DOC_ID_PATH_HASH_LENGTH = 12

logger = logging.getLogger(__name__)


class DocumentService:
    """Deep module for document operations.

    Encapsulates document CRUD, version tracking, and wikilink dependency
    management. The caller never needs to coordinate multiple services —
    each public method handles the complete operation atomically.
    """

    def __init__(self, db: Session):
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self.version_repo = VersionRepository(db)
        self.dep_service = DependencyService(db)

    def generate_doc_id(self, repo_url: Optional[str], path: str = "", title: str = "", doc_type: str = "") -> str:
        """Generate stable document ID."""
        # Standalone documents (no repository)
        if not repo_url:
            full_path = f"{path}/{title}" if path else title
            path_hash = hashlib.sha256(full_path.encode()).hexdigest()[:DOC_ID_PATH_HASH_LENGTH]
            doc_id = f"doc-standalone-{path_hash}"
            logger.debug(f"Generated standalone doc_id={doc_id} for path={path}, title={title}")
            return doc_id

        repo_hash = hashlib.sha256(repo_url.encode()).hexdigest()[:DOC_ID_REPO_HASH_LENGTH]

        if path or title:
            full_path = f"{path}/{title}" if path else title
            path_hash = hashlib.sha256(full_path.encode()).hexdigest()[:DOC_ID_PATH_HASH_LENGTH]
            doc_id = f"doc-{repo_hash}-{path_hash}"
            logger.debug(f"Generated doc_id={doc_id} for repo={repo_url}, path={path}, title={title}")
            return doc_id

        if doc_type:
            doc_id = f"doc-{repo_hash}-{doc_type}"
            logger.debug(f"Generated legacy doc_id={doc_id} for repo={repo_url}, doc_type={doc_type}")
            return doc_id

        logger.warning(f"Generating default doc_id for repo={repo_url}")
        return f"doc-{repo_hash}-default"

    def create_or_update_document(self, document: DocumentCreate, commit: bool = True) -> tuple[Document, bool]:
        """Create new document or update existing one (upsert).

        Handles the full lifecycle: persist document, create version,
        and update wikilink dependencies — all in one call.
        Returns (document, is_new) tuple.
        """
        doc_type = document.doc_type
        if not doc_type and document.path:
            doc_type = document.path.split('/')[0] if document.path else "root"

        doc_id = self.generate_doc_id(
            document.repo_url,
            document.path,
            document.title,
            doc_type
        )

        existing = self.doc_repo.get_by_id_optional(doc_id)
        is_new = existing is None

        if existing:
            # Route through update_document() to get optimistic locking,
            # version creation, and dependency refresh in one path.
            update_data = DocumentUpdate(
                content=document.content,
                author_type=document.author_type,
                author_metadata=document.author_metadata,
                version=existing.version,
            )
            db_document = self.update_document(doc_id, update_data, commit=False)
        else:
            db_document = self.doc_repo.create(doc_id, document)

            version = VersionCreate(
                doc_id=doc_id,
                content=document.content,
                author_type=document.author_type,
                author_metadata=document.author_metadata,
            )
            self.version_repo.create(version)

            self.dep_service.replace_document_dependencies(doc_id, document.content)
            self.dep_service.update_incoming_dependencies(doc_id, document.title)

        if commit:
            self.db.commit()
        return db_document, is_new

    def update_document(self, doc_id: str, update_data: DocumentUpdate, commit: bool = True) -> Document:
        """Update document content, create new version, and refresh wikilink dependencies.

        When update_data.version is provided, checks it matches the current
        version in the database. Raises ConflictError (409) on mismatch,
        indicating a concurrent modification.
        """
        existing = self.doc_repo.get_by_id(doc_id)

        if update_data.version is not None and update_data.version != existing.version:
            raise ConflictError(doc_id)

        updated = self.doc_repo.update(doc_id, update_data)

        version = VersionCreate(
            doc_id=doc_id,
            content=update_data.content,
            author_type=update_data.author_type,
            author_metadata=update_data.author_metadata
        )
        self.version_repo.create(version)

        # Refresh wikilink dependencies from new content
        self.dep_service.replace_document_dependencies(doc_id, update_data.content)

        if commit:
            self.db.commit()
        return updated

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get document by ID. Returns None if not found (caller decides on 404)."""
        return self.doc_repo.get_by_id_optional(doc_id)

    def list_documents(self, skip: int = 0, limit: int = 100, path_prefix: Optional[str] = None, repo_url: Optional[str] = None, allowed_prefixes: Optional[list[str]] = None) -> List[DocumentListResponse]:
        """List all documents."""
        documents = self.doc_repo.get_all(skip, limit, path_prefix, repo_url=repo_url, allowed_prefixes=allowed_prefixes)
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
                version=doc.version,
            )
            for doc in documents
        ]

    def get_tracked_repo_urls(self) -> list[str]:
        """Get distinct repo URLs that have documentation."""
        return self.doc_repo.get_tracked_repo_urls()

    def delete_document(self, doc_id: str) -> bool:
        """Soft-delete document (moves to trash). Idempotent."""
        result = self.doc_repo.soft_delete(doc_id)
        self.db.commit()
        return result

    def restore_document(self, doc_id: str) -> Document:
        """Restore a soft-deleted document. Raises DocumentNotFoundError if not found."""
        result = self.doc_repo.restore(doc_id)
        self.db.commit()
        return result

    def permanent_delete_document(self, doc_id: str) -> bool:
        """Permanently delete a document. Idempotent."""
        result = self.doc_repo.permanent_delete(doc_id)
        self.db.commit()
        return result

    def list_trash(self, skip: int = 0, limit: int = 100, allowed_prefixes: Optional[list[str]] = None) -> List[DocumentListResponse]:
        """List soft-deleted documents."""
        documents = self.doc_repo.get_deleted(skip, limit, allowed_prefixes=allowed_prefixes)
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
                version=doc.version,
                deleted_at=doc.deleted_at
            )
            for doc in documents
        ]

    def purge_expired_trash(self, days: int = 30) -> int:
        """Permanently delete documents in trash older than `days`."""
        count = self.doc_repo.purge_expired(days)
        if count > 0:
            self.db.commit()
        return count

    def move_document(self, doc_id: str, target_path: str, commit: bool = True) -> Document:
        """Move a document to a different folder path.

        Handles wikilink updates internally when the document's crate (repo_name)
        changes — other documents' wikilinks pointing to this doc are updated.
        """
        doc, old_repo_name, new_repo_name = self._move_document_impl(doc_id, target_path)

        # If the crate changed, update wikilinks in other documents that reference this one
        if old_repo_name and new_repo_name and old_repo_name != new_repo_name:
            self.dep_service.update_wikilinks_on_move(doc_id, old_repo_name, new_repo_name)

        if commit:
            self.db.commit()
        return doc

    def _move_document_impl(self, doc_id: str, target_path: str) -> tuple[Document, str | None, str | None]:
        """Move implementation without commit — used by both move_document and execute_batch.

        Returns (document, old_repo_name, new_repo_name) for caller to update wikilinks if needed.
        """
        doc = self.doc_repo.get_by_id(doc_id)
        old_repo_name = doc.repo_name
        target_path = target_path.strip().strip('/')
        doc.path = target_path
        self.db.flush()
        self.db.refresh(doc)

        return doc, old_repo_name, doc.repo_name

    def update_keywords(self, doc_id: str, keywords: list[str]) -> Document:
        """Update a document's keywords."""
        doc = self.doc_repo.get_by_id(doc_id)
        doc.keywords = keywords
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def update_repo_url(self, doc_id: str, repo_url: str) -> Document:
        """Update a document's git repository URL."""
        doc = self.doc_repo.get_by_id(doc_id)
        doc.repo_url = repo_url or None
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def search_documents(
        self,
        query: str,
        limit: int = 20,
        path_prefix: Optional[str] = None,
        keywords: Optional[list] = None,
        date_from=None,
        date_to=None,
        allowed_prefixes: Optional[list[str]] = None,
    ) -> list[SearchResultResponse]:
        """Search documents using FTS (with LIKE fallback)."""
        return self.doc_repo.search_fts(
            query, limit, path_prefix, keywords, date_from, date_to,
            allowed_prefixes=allowed_prefixes,
        )

    def get_recent_documents(self, limit: int = 20, allowed_prefixes: Optional[list[str]] = None) -> List[Document]:
        """Get the most recently updated documents."""
        return self.doc_repo.get_recent(limit, allowed_prefixes=allowed_prefixes)

    def execute_batch_authorized(
        self,
        operation: str,
        doc_ids: list[str],
        params: dict,
        grants: list,
        is_service_account: bool = False,
    ) -> BatchResult:
        """Execute a batch operation with permission filtering.

        Service accounts can only delete AI-authored documents.
        Normal users are filtered by path-based grants.
        Denied documents are reported as errors, not silently dropped.
        """
        from ..services.permission_service import check_permission

        allowed_ids: list[str] = []
        denied_ids: list[str] = []

        if is_service_account and operation == "delete":
            for doc_id in doc_ids:
                doc = self.get_document(doc_id)
                if doc is None:
                    denied_ids.append(doc_id)
                    continue
                latest = self.version_repo.get_latest(doc_id)
                if latest and latest.author_type == "ai":
                    allowed_ids.append(doc_id)
                else:
                    denied_ids.append(doc_id)
        else:
            action = "delete" if operation == "delete" else "edit"
            for doc_id in doc_ids:
                doc = self.get_document(doc_id)
                if doc is not None and check_permission(grants, doc.path, action):
                    allowed_ids.append(doc_id)
                else:
                    denied_ids.append(doc_id)

        result = self.execute_batch(operation, allowed_ids, params)

        if denied_ids:
            denied_errors = [BatchError(doc_id=doc_id, error="Access denied") for doc_id in denied_ids]
            return BatchResult(
                total=result.total + len(denied_ids),
                succeeded=result.succeeded,
                failed=result.failed + len(denied_ids),
                errors=result.errors + denied_errors,
            )

        return result

    def execute_batch(self, operation: str, doc_ids: list[str], params: dict) -> BatchResult:
        """Execute a batch operation on multiple documents.

        Returns a BatchResult with total, succeeded, failed, errors.
        Empty doc_ids returns zero counts (not an error).
        Partial failures are reported in errors, not raised as exceptions.
        """
        total = len(doc_ids)
        succeeded = 0
        errors: list[BatchError] = []

        for doc_id in doc_ids:
            savepoint = self.db.begin_nested()
            try:
                if operation == "delete":
                    self.doc_repo.soft_delete(doc_id)
                    succeeded += 1
                elif operation == "move":
                    target_path = params.get("target_path", "")
                    self._move_document_impl(doc_id, target_path)
                    succeeded += 1
                elif operation == "add_keywords":
                    kw_to_add = params.get("keywords", [])
                    doc = self.doc_repo.get_by_id(doc_id)
                    existing = doc.keywords or []
                    doc.keywords = list(set(existing + kw_to_add))
                    succeeded += 1
                elif operation == "remove_keywords":
                    kw_to_remove = set(params.get("keywords", []))
                    doc = self.doc_repo.get_by_id(doc_id)
                    doc.keywords = [k for k in (doc.keywords or []) if k not in kw_to_remove]
                    succeeded += 1
                else:
                    errors.append(BatchError(doc_id=doc_id, error=f"Unknown operation: {operation}"))
                savepoint.commit()
            except Exception as e:
                savepoint.rollback()
                logger.warning("Batch %s failed for %s: %s", operation, doc_id, e, exc_info=True)
                errors.append(BatchError(doc_id=doc_id, error=str(e)))

        self.db.commit()
        return BatchResult(
            total=total,
            succeeded=succeeded,
            failed=total - succeeded,
            errors=errors,
        )

    def get_version(self, version_id: str) -> Optional['Version']:
        """Get specific version by ID. Returns None if not found."""
        return self.version_repo.get_by_id_optional(version_id)

    def get_document_versions(self, doc_id: str, skip: int = 0, limit: int = 50) -> list:
        """Get all versions for a document with pagination."""
        return self.version_repo.get_by_document(doc_id, skip, limit)

    def get_latest_version(self, doc_id: str) -> Optional['Version']:
        """Get latest version for a document."""
        return self.version_repo.get_latest(doc_id)
