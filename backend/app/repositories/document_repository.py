"""Document repository for database operations.

Owns all document query logic including soft-delete filtering.
Every read query uses _active_query() to exclude soft-deleted documents,
so callers never need to think about the deleted_at column.
"""

from sqlalchemy.orm import Session, Query
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from ..models import Document
from ..schemas.document import DocumentCreate, DocumentUpdate
from ..services.content_utils import generate_content_preview


class DocumentRepository:
    """Repository for document CRUD operations.

    All read methods automatically exclude soft-deleted documents.
    Use get_deleted() to access the trash, and soft_delete/restore/permanent_delete
    for lifecycle management.
    """

    def __init__(self, db: Session):
        self.db = db

    def _active_query(self) -> Query:
        """Base query that excludes soft-deleted documents."""
        return self.db.query(Document).filter(Document.deleted_at.is_(None))

    def create(self, doc_id: str, document: DocumentCreate) -> Document:
        """Create a new document."""
        content_preview = generate_content_preview(document.content)

        db_document = Document(
            id=doc_id,
            repo_url=document.repo_url,
            repo_name=document.repo_name,
            doc_type=document.doc_type,
            keywords=getattr(document, 'keywords', []) or [],
            path=document.path,
            title=document.title,
            content=document.content,
            content_preview=content_preview,
            generation_count=1
        )
        self.db.add(db_document)
        self.db.commit()
        self.db.refresh(db_document)
        return db_document

    def get_by_id(self, doc_id: str) -> Optional[Document]:
        """Get active (non-deleted) document by ID."""
        return self._active_query().filter(Document.id == doc_id).first()

    def get_by_id_including_deleted(self, doc_id: str) -> Optional[Document]:
        """Get document by ID regardless of soft-delete status."""
        return self.db.query(Document).filter(Document.id == doc_id).first()

    def get_by_repo_and_type(self, repo_url: str, doc_type: str) -> Optional[Document]:
        """Get active document by repository URL and type."""
        return self._active_query().filter(
            Document.repo_url == repo_url,
            Document.doc_type == doc_type
        ).first()

    def get_all(self, skip: int = 0, limit: int = 100, path_prefix: Optional[str] = None) -> List[Document]:
        """Get all active documents with pagination, optionally filtered by path prefix."""
        query = self._active_query()
        if path_prefix:
            query = query.filter(
                (Document.path == path_prefix) |
                (Document.path.like(f"{path_prefix}/%"))
            )
        return query.offset(skip).limit(limit).all()

    def update(self, doc_id: str, document: DocumentUpdate) -> Optional[Document]:
        """Update document content."""
        db_document = self.get_by_id(doc_id)
        if not db_document:
            return None

        db_document.content = document.content
        db_document.content_preview = generate_content_preview(document.content)
        db_document.generation_count += 1

        self.db.commit()
        self.db.refresh(db_document)
        return db_document

    def delete(self, doc_id: str) -> bool:
        """Hard delete document. Prefer soft_delete() for user-facing operations."""
        db_document = self.db.query(Document).filter(Document.id == doc_id).first()
        if not db_document:
            return False

        self.db.delete(db_document)
        self.db.commit()
        return True

    def soft_delete(self, doc_id: str) -> bool:
        """Mark document as deleted. Idempotent — succeeds if already deleted or not found."""
        db_document = self.db.query(Document).filter(Document.id == doc_id).first()
        if not db_document:
            return False

        if db_document.deleted_at is None:
            db_document.deleted_at = datetime.now(timezone.utc)
            self.db.commit()
        return True

    def restore(self, doc_id: str) -> Optional[Document]:
        """Restore a soft-deleted document. Idempotent — returns doc even if not deleted."""
        db_document = self.db.query(Document).filter(Document.id == doc_id).first()
        if not db_document:
            return None

        if db_document.deleted_at is not None:
            db_document.deleted_at = None
            self.db.commit()
            self.db.refresh(db_document)
        return db_document

    def permanent_delete(self, doc_id: str) -> bool:
        """Hard delete a document (typically one already in trash). Idempotent."""
        db_document = self.db.query(Document).filter(Document.id == doc_id).first()
        if not db_document:
            return True  # Already gone — idempotent

        self.db.delete(db_document)
        self.db.commit()
        return True

    def get_deleted(self, skip: int = 0, limit: int = 100) -> List[Document]:
        """Get soft-deleted documents (trash), ordered by deletion time descending."""
        return (
            self.db.query(Document)
            .filter(Document.deleted_at.isnot(None))
            .order_by(Document.deleted_at.desc())
            .offset(skip).limit(limit).all()
        )

    def purge_expired(self, days: int = 30) -> int:
        """Permanently delete documents that have been in trash longer than `days`."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        expired = (
            self.db.query(Document)
            .filter(Document.deleted_at.isnot(None))
            .filter(Document.deleted_at < cutoff)
            .all()
        )
        count = len(expired)
        for doc in expired:
            self.db.delete(doc)
        if count > 0:
            self.db.commit()
        return count

    def search(self, query: str, limit: int = 20) -> List[Document]:
        """Simple LIKE search fallback (excludes soft-deleted)."""
        return self._active_query().filter(
            Document.content.contains(query)
        ).limit(limit).all()

    def search_fts(
        self,
        query: str,
        limit: int = 20,
        path_prefix: Optional[str] = None,
        keywords: Optional[list] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> list[dict]:
        """Full-text search using FTS5 with ranking and snippets.

        Returns dicts with keys: id, title, path, doc_type, keywords, repo_name,
        content_preview, updated_at, generation_count, rank, snippet.
        Falls back to LIKE search if FTS5 table doesn't exist.
        """
        try:
            # Build FTS5 query with prefix matching
            fts_query = query.strip()
            if fts_query and not any(c in fts_query for c in ['"', '*', 'OR', 'AND', 'NOT']):
                # Add prefix matching for simple queries
                terms = fts_query.split()
                fts_query = ' '.join(f'"{t}"*' for t in terms if t)

            sql = """
                SELECT
                    d.id, d.title, d.path, d.doc_type, d.keywords, d.repo_name,
                    d.content_preview, d.updated_at, d.generation_count,
                    bm25(documents_fts) as rank,
                    snippet(documents_fts, 2, '<mark>', '</mark>', '...', 40) as snippet
                FROM documents_fts fts
                JOIN documents d ON d.id = fts.doc_id
                WHERE documents_fts MATCH :query
                AND d.deleted_at IS NULL
            """
            params: dict = {"query": fts_query, "limit": limit}

            if path_prefix:
                sql += " AND (d.path = :path_prefix OR d.path LIKE :path_like)"
                params["path_prefix"] = path_prefix
                params["path_like"] = f"{path_prefix}/%"

            if date_from:
                sql += " AND d.updated_at >= :date_from"
                params["date_from"] = date_from.isoformat()

            if date_to:
                sql += " AND d.updated_at <= :date_to"
                params["date_to"] = date_to.isoformat()

            sql += " ORDER BY rank LIMIT :limit"

            rows = self.db.execute(text(sql), params).fetchall()

            results = []
            for row in rows:
                kw = row[4]
                if isinstance(kw, str):
                    import json
                    try:
                        kw = json.loads(kw)
                    except (json.JSONDecodeError, TypeError):
                        kw = []

                # Apply keyword filter in Python (simpler than SQL JSON filtering)
                if keywords:
                    if not any(k in (kw or []) for k in keywords):
                        continue

                results.append({
                    "id": row[0],
                    "title": row[1],
                    "path": row[2],
                    "doc_type": row[3] or "",
                    "keywords": kw or [],
                    "repo_name": row[5],
                    "content_preview": row[6],
                    "updated_at": row[7],
                    "generation_count": row[8],
                    "rank": row[9],
                    "snippet": row[10],
                })
            return results

        except Exception:
            # FTS5 table may not exist yet — fall back to LIKE search
            docs = self.search(query, limit)
            return [
                {
                    "id": d.id,
                    "title": d.title,
                    "path": d.path,
                    "doc_type": d.doc_type or "",
                    "keywords": d.keywords or [],
                    "repo_name": d.repo_name,
                    "content_preview": d.content_preview,
                    "updated_at": d.updated_at,
                    "generation_count": d.generation_count,
                    "rank": 0.0,
                    "snippet": None,
                }
                for d in docs
            ]

    def get_recent(self, limit: int = 20) -> List[Document]:
        """Get most recently updated active documents."""
        return (
            self._active_query()
            .order_by(Document.updated_at.desc())
            .limit(limit).all()
        )

    def move_folder(self, source_path: str, target_path: str) -> int:
        """Move folder by updating path prefixes (active docs only)."""
        affected_docs = self._active_query().filter(
            (Document.path == source_path) |
            (Document.path.like(f"{source_path}/%"))
        ).all()

        for doc in affected_docs:
            if doc.path == source_path:
                doc.path = target_path
            else:
                relative_path = doc.path[len(source_path) + 1:]
                doc.path = f"{target_path}/{relative_path}"

        self.db.commit()
        return len(affected_docs)
