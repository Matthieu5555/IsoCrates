"""Document service with business logic."""

from sqlalchemy.orm import Session
from typing import List, Optional
import hashlib
import logging
from ..models import Document
from ..schemas.document import DocumentCreate, DocumentUpdate, DocumentListResponse, DocumentKeywordsUpdate
from ..repositories import DocumentRepository, VersionRepository
from ..schemas.version import VersionCreate
from ..services.dependency_service import DependencyService
from ..exceptions import DocumentNotFoundError, ValidationError

DOC_ID_REPO_HASH_LENGTH = 12
DOC_ID_PATH_HASH_LENGTH = 12

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document operations with business logic."""

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

    def create_or_update_document(self, document: DocumentCreate) -> Document:
        """Create new document or update existing one (upsert)."""
        doc_type = document.doc_type
        if not doc_type and document.path:
            doc_type = document.path.split('/')[0] if document.path else "root"

        doc_id = self.generate_doc_id(
            document.repo_url,
            document.path,
            document.title,
            doc_type
        )

        existing = self.doc_repo.get_by_id(doc_id)

        if existing:
            update_data = DocumentUpdate(
                content=document.content,
                author_type=document.author_type,
                author_metadata=document.author_metadata
            )
            db_document = self.doc_repo.update(doc_id, update_data)
        else:
            db_document = self.doc_repo.create(doc_id, document)

        version = VersionCreate(
            doc_id=doc_id,
            content=document.content,
            author_type=document.author_type,
            author_metadata=document.author_metadata
        )
        self.version_repo.create(version)
        self.dep_service.replace_document_dependencies(doc_id, document.content)

        return db_document

    def update_document(self, doc_id: str, update_data: DocumentUpdate) -> Document:
        """Update document content and create new version."""
        existing = self.doc_repo.get_by_id(doc_id)
        if not existing:
            raise DocumentNotFoundError(doc_id)

        updated = self.doc_repo.update(doc_id, update_data)

        version = VersionCreate(
            doc_id=doc_id,
            content=update_data.content,
            author_type=update_data.author_type,
            author_metadata=update_data.author_metadata
        )
        self.version_repo.create(version)
        self.dep_service.replace_document_dependencies(doc_id, update_data.content)

        return updated

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get document by ID."""
        return self.doc_repo.get_by_id(doc_id)

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
                generation_count=doc.generation_count
            )
            for doc in documents
        ]

    def get_tracked_repo_urls(self) -> list[str]:
        """Get distinct repo URLs that have documentation."""
        return self.doc_repo.get_tracked_repo_urls()

    def delete_document(self, doc_id: str) -> bool:
        """Soft-delete document (moves to trash). Idempotent."""
        return self.doc_repo.soft_delete(doc_id)

    def restore_document(self, doc_id: str) -> Optional[Document]:
        """Restore a soft-deleted document. Returns the document, or None if not found."""
        return self.doc_repo.restore(doc_id)

    def permanent_delete_document(self, doc_id: str) -> bool:
        """Permanently delete a document. Idempotent."""
        return self.doc_repo.permanent_delete(doc_id)

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
                deleted_at=doc.deleted_at
            )
            for doc in documents
        ]

    def purge_expired_trash(self, days: int = 30) -> int:
        """Permanently delete documents in trash older than `days`."""
        return self.doc_repo.purge_expired(days)

    def move_document(self, doc_id: str, target_path: str) -> Document:
        """Move a document to a different folder path.

        Also updates wikilinks in other documents if the document's
        repo_name is used as a link target.
        """
        doc = self.doc_repo.get_by_id(doc_id)
        if not doc:
            raise DocumentNotFoundError(doc_id)

        old_repo_name = doc.repo_name
        target_path = target_path.strip().strip('/')
        doc.path = target_path
        self.db.commit()
        self.db.refresh(doc)

        # Update wikilinks in referring documents if repo_name changed.
        # Note: repo_name is a stable identifier that doesn't derive from path,
        # so a path-only move won't trigger this. This guard exists for future
        # rename operations that modify repo_name directly.
        if old_repo_name and doc.repo_name and old_repo_name != doc.repo_name:
            self.dep_service.update_wikilinks_on_move(doc_id, old_repo_name, doc.repo_name)

        return doc

    def update_keywords(self, doc_id: str, keywords: list[str]) -> Document:
        """Update a document's keywords."""
        doc = self.doc_repo.get_by_id(doc_id)
        if not doc:
            raise DocumentNotFoundError(doc_id)
        doc.keywords = keywords
        self.db.commit()
        self.db.refresh(doc)
        return doc

    def update_repo_url(self, doc_id: str, repo_url: str) -> Document:
        """Update a document's git repository URL."""
        doc = self.doc_repo.get_by_id(doc_id)
        if not doc:
            raise DocumentNotFoundError(doc_id)
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
    ) -> list[dict]:
        """Search documents using FTS5 (with LIKE fallback). Returns dicts."""
        return self.doc_repo.search_fts(
            query, limit, path_prefix, keywords, date_from, date_to,
            allowed_prefixes=allowed_prefixes,
        )

    def get_recent_documents(self, limit: int = 20, allowed_prefixes: Optional[list[str]] = None) -> List[Document]:
        """Get the most recently updated documents."""
        return self.doc_repo.get_recent(limit, allowed_prefixes=allowed_prefixes)

    def execute_batch(self, operation: str, doc_ids: list[str], params: dict) -> dict:
        """Execute a batch operation on multiple documents.

        Returns a BatchResult dict with total, succeeded, failed, errors.
        Empty doc_ids returns zero counts (not an error).
        Partial failures are reported in errors, not raised as exceptions.
        """
        total = len(doc_ids)
        succeeded = 0
        errors = []

        for doc_id in doc_ids:
            try:
                if operation == "delete":
                    self.doc_repo.soft_delete(doc_id)
                    succeeded += 1
                elif operation == "move":
                    target_path = params.get("target_path", "")
                    self.move_document(doc_id, target_path)
                    succeeded += 1
                elif operation == "add_keywords":
                    kw_to_add = params.get("keywords", [])
                    doc = self.doc_repo.get_by_id(doc_id)
                    if doc:
                        existing = doc.keywords or []
                        doc.keywords = list(set(existing + kw_to_add))
                        succeeded += 1
                    else:
                        errors.append({"doc_id": doc_id, "error": "Not found"})
                elif operation == "remove_keywords":
                    kw_to_remove = set(params.get("keywords", []))
                    doc = self.doc_repo.get_by_id(doc_id)
                    if doc:
                        doc.keywords = [k for k in (doc.keywords or []) if k not in kw_to_remove]
                        succeeded += 1
                    else:
                        errors.append({"doc_id": doc_id, "error": "Not found"})
                else:
                    errors.append({"doc_id": doc_id, "error": f"Unknown operation: {operation}"})
            except Exception as e:
                errors.append({"doc_id": doc_id, "error": str(e)})

        self.db.commit()
        return {
            "total": total,
            "succeeded": succeeded,
            "failed": total - succeeded,
            "errors": errors,
        }

    def resolve_wikilink(self, target: str) -> Optional[str]:
        """Resolve a wikilink target to a document ID. Delegates to DependencyService."""
        return self.dep_service._resolve_wikilink(target)

    def get_version(self, version_id: str):
        """Get specific version by ID."""
        return self.version_repo.get_by_id(version_id)

    def get_document_versions(self, doc_id: str, skip: int = 0, limit: int = 50):
        """Get all versions for a document with pagination."""
        return self.version_repo.get_by_document(doc_id, skip, limit)

    def get_latest_version(self, doc_id: str):
        """Get latest version for a document."""
        return self.version_repo.get_latest(doc_id)
