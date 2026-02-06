"""Document repository for database operations.

Owns all document query logic including soft-delete filtering.
Every read query uses _base_query() to exclude soft-deleted documents,
so callers never need to think about the deleted_at column.
"""

from sqlalchemy.orm import Query
from sqlalchemy import text, or_
import sqlalchemy.exc
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from ..models import Document
from ..schemas.document import DocumentCreate, DocumentUpdate, SearchResultResponse, SimilarDocumentResponse
from ..database import is_postgresql
from ..exceptions import DocumentNotFoundError
from .base import BaseRepository

# Maximum length of content preview stored alongside each document.
# 500 chars ≈ 3-4 sentences, enough for meaningful list-view previews
# without bloating response payloads. Used by create() and update().
CONTENT_PREVIEW_LENGTH = 500


def generate_content_preview(content: str) -> str:
    """Generate a preview excerpt from document content."""
    if len(content) <= CONTENT_PREVIEW_LENGTH:
        return content
    return content[:CONTENT_PREVIEW_LENGTH]


class DocumentRepository(BaseRepository[Document]):
    """Repository for document CRUD operations.

    All read methods automatically exclude soft-deleted documents via
    _base_query().  Use get_deleted() to access the trash, and
    soft_delete/restore/permanent_delete for lifecycle management.
    """

    model_class = Document
    not_found_error = DocumentNotFoundError

    def _base_query(self) -> Query:
        """Exclude soft-deleted documents from all default queries."""
        return self.db.query(Document).filter(Document.deleted_at.is_(None))

    @staticmethod
    def _grant_filter(allowed_prefixes: list[str]):
        """Build a SQLAlchemy OR filter for path-prefix grants.

        Each prefix matches documents whose path equals the prefix or starts
        with prefix + '/'.  An empty string means root access (matches all).
        Returns None when no filtering is needed (root access or no prefixes).
        """
        if not allowed_prefixes:
            return Document.id.is_(None)  # no grants → match nothing

        # Root grant present → no filtering needed
        if "" in allowed_prefixes:
            return None

        clauses = []
        for prefix in allowed_prefixes:
            clauses.append(Document.path == prefix)
            clauses.append(Document.path.like(f"{prefix}/%"))
        return or_(*clauses)

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
            description=getattr(document, 'description', None),
            generation_count=1
        )
        self.db.add(db_document)
        self.db.flush()
        self.db.refresh(db_document)
        return db_document

    # get_by_id and get_by_id_optional are inherited from BaseRepository
    # and use _base_query(), so they automatically exclude soft-deleted docs.

    def get_by_id_including_deleted(self, doc_id: str) -> Optional[Document]:
        """Get document by ID regardless of soft-delete status."""
        return self.db.query(Document).filter(Document.id == doc_id).first()

    def get_by_repo_and_type(self, repo_url: str, doc_type: str) -> Optional[Document]:
        """Get active document by repository URL and type."""
        return self._base_query().filter(
            Document.repo_url == repo_url,
            Document.doc_type == doc_type
        ).first()

    def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        path_prefix: Optional[str] = None,
        repo_url: Optional[str] = None,
        allowed_prefixes: Optional[list[str]] = None,
    ) -> List[Document]:
        """Get all active documents with pagination, optionally filtered by path prefix or repo URL.

        When *allowed_prefixes* is provided, only documents under those path
        prefixes are returned.  This pushes permission filtering into SQL so
        pagination counts are accurate.
        """
        query = self._base_query()
        if path_prefix:
            query = query.filter(
                (Document.path == path_prefix) |
                (Document.path.like(f"{path_prefix}/%"))
            )
        if repo_url:
            query = query.filter(Document.repo_url == repo_url)
        if allowed_prefixes is not None:
            grant_filter = self._grant_filter(allowed_prefixes)
            if grant_filter is not None:
                query = query.filter(grant_filter)
        return query.offset(skip).limit(limit).all()

    def get_tracked_repo_urls(self) -> List[str]:
        """Get distinct repo_url values from active documents."""
        rows = (
            self._base_query()
            .filter(Document.repo_url.isnot(None), Document.repo_url != "")
            .with_entities(Document.repo_url)
            .distinct()
            .all()
        )
        return [row[0] for row in rows]

    def update(self, doc_id: str, document: DocumentUpdate) -> Document:
        """Update document content. Raises DocumentNotFoundError."""
        db_document = self.get_by_id(doc_id)
        db_document.content = document.content
        db_document.content_preview = generate_content_preview(document.content)
        db_document.generation_count += 1
        db_document.version = (db_document.version or 0) + 1

        if document.description is not None:
            db_document.description = document.description
            # Clear embedding — content changed, needs re-embedding
            db_document.embedding_model = None

        self.db.flush()
        self.db.refresh(db_document)
        return db_document

    def delete(self, doc_id: str) -> bool:
        """Hard delete document. Prefer soft_delete() for user-facing operations."""
        db_document = self.db.query(Document).filter(Document.id == doc_id).first()
        if not db_document:
            return False

        self.db.delete(db_document)
        return True

    def soft_delete(self, doc_id: str) -> bool:
        """Mark document as deleted. Idempotent — succeeds if already deleted or not found."""
        db_document = self.db.query(Document).filter(Document.id == doc_id).first()
        if not db_document:
            return False

        if db_document.deleted_at is None:
            db_document.deleted_at = datetime.now(timezone.utc)
        return True

    def restore(self, doc_id: str) -> Document:
        """Restore a soft-deleted document. Raises DocumentNotFoundError. Idempotent if not deleted."""
        db_document = self.db.query(Document).filter(Document.id == doc_id).first()
        if not db_document:
            raise DocumentNotFoundError(doc_id)

        if db_document.deleted_at is not None:
            db_document.deleted_at = None
            self.db.flush()
            self.db.refresh(db_document)
        return db_document

    def permanent_delete(self, doc_id: str) -> bool:
        """Hard delete a document (typically one already in trash). Idempotent."""
        db_document = self.db.query(Document).filter(Document.id == doc_id).first()
        if not db_document:
            return True  # Already gone — idempotent

        self.db.delete(db_document)
        return True

    def get_deleted(self, skip: int = 0, limit: int = 100, allowed_prefixes: Optional[list[str]] = None) -> List[Document]:
        """Get soft-deleted documents (trash), ordered by deletion time descending."""
        query = (
            self.db.query(Document)
            .filter(Document.deleted_at.isnot(None))
        )
        if allowed_prefixes is not None:
            grant_filter = self._grant_filter(allowed_prefixes)
            if grant_filter is not None:
                query = query.filter(grant_filter)
        return query.order_by(Document.deleted_at.desc()).offset(skip).limit(limit).all()

    def purge_expired(self, days: int = 30) -> int:
        """Permanently delete documents that have been in trash longer than `days`."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        count = (
            self.db.query(Document)
            .filter(Document.deleted_at.isnot(None))
            .filter(Document.deleted_at < cutoff)
            .delete(synchronize_session="fetch")
        )
        return count

    def search(self, query: str, limit: int = 20, allowed_prefixes: Optional[list[str]] = None) -> List[Document]:
        """Simple LIKE search fallback (excludes soft-deleted)."""
        q = self._base_query().filter(Document.content.contains(query))
        if allowed_prefixes is not None:
            grant_filter = self._grant_filter(allowed_prefixes)
            if grant_filter is not None:
                q = q.filter(grant_filter)
        return q.limit(limit).all()

    def search_fts(
        self,
        query: str,
        limit: int = 20,
        path_prefix: Optional[str] = None,
        keywords: Optional[list] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        allowed_prefixes: Optional[list[str]] = None,
    ) -> list[SearchResultResponse]:
        """Full-text search with ranking and snippets.

        Uses PostgreSQL tsvector/tsquery or SQLite FTS5 depending on database.
        Falls back to LIKE search if FTS is not available.
        """
        if is_postgresql():
            return self._search_fts_postgresql(
                query, limit, path_prefix, keywords, date_from, date_to, allowed_prefixes
            )
        else:
            return self._search_fts_sqlite(
                query, limit, path_prefix, keywords, date_from, date_to, allowed_prefixes
            )

    def _search_fts_postgresql(
        self,
        query: str,
        limit: int,
        path_prefix: Optional[str],
        keywords: Optional[list],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        allowed_prefixes: Optional[list[str]],
    ) -> list[SearchResultResponse]:
        """PostgreSQL full-text search using tsvector/tsquery."""
        try:
            # Build PostgreSQL tsquery - convert space-separated terms to AND query
            search_query = query.strip()
            if search_query and not any(c in search_query for c in ['&', '|', '!', ':']):
                # Convert simple query to tsquery format with prefix matching
                terms = search_query.split()
                search_query = ' & '.join(f"{t}:*" for t in terms if t)

            sql = """
                SELECT
                    d.id, d.title, d.path, d.doc_type, d.keywords, d.repo_name,
                    d.content_preview, d.updated_at, d.generation_count,
                    ts_rank(to_tsvector('english', COALESCE(d.title, '') || ' ' || COALESCE(d.content, '')),
                            to_tsquery('english', :query)) as rank,
                    ts_headline('english', COALESCE(d.content, ''),
                               to_tsquery('english', :query),
                               'StartSel=<mark>, StopSel=</mark>, MaxWords=40, MinWords=20') as snippet,
                    d.description
                FROM documents d
                WHERE to_tsvector('english', COALESCE(d.title, '') || ' ' || COALESCE(d.content, ''))
                      @@ to_tsquery('english', :query)
                AND d.deleted_at IS NULL
            """
            params: dict = {"query": search_query, "limit": limit}

            if path_prefix:
                sql += " AND (d.path = :path_prefix OR d.path LIKE :path_like)"
                params["path_prefix"] = path_prefix
                params["path_like"] = f"{path_prefix}/%"

            if allowed_prefixes is not None and "" not in allowed_prefixes:
                if not allowed_prefixes:
                    return []
                grant_clauses = []
                for i, prefix in enumerate(allowed_prefixes):
                    grant_clauses.append(f"(d.path = :gp_exact_{i} OR d.path LIKE :gp_like_{i})")
                    params[f"gp_exact_{i}"] = prefix
                    params[f"gp_like_{i}"] = f"{prefix}/%"
                sql += f" AND ({' OR '.join(grant_clauses)})"

            if date_from:
                sql += " AND d.updated_at >= :date_from"
                params["date_from"] = date_from

            if date_to:
                sql += " AND d.updated_at <= :date_to"
                params["date_to"] = date_to

            sql += " ORDER BY rank DESC LIMIT :limit"

            rows = self.db.execute(text(sql), params).fetchall()
            return self._process_fts_results(rows, keywords)

        except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.ProgrammingError):
            # Fall back to LIKE search
            return self._fallback_like_search(query, limit, allowed_prefixes)

    def _search_fts_sqlite(
        self,
        query: str,
        limit: int,
        path_prefix: Optional[str],
        keywords: Optional[list],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        allowed_prefixes: Optional[list[str]],
    ) -> list[SearchResultResponse]:
        """SQLite FTS5 full-text search."""
        try:
            # Build FTS5 query with prefix matching
            fts_query = query.strip()
            if fts_query and not any(c in fts_query for c in ['"', '*', 'OR', 'AND', 'NOT']):
                terms = fts_query.split()
                fts_query = ' '.join(f'"{t}"*' for t in terms if t)

            sql = """
                SELECT
                    d.id, d.title, d.path, d.doc_type, d.keywords, d.repo_name,
                    d.content_preview, d.updated_at, d.generation_count,
                    bm25(documents_fts) as rank,
                    snippet(documents_fts, 2, '<mark>', '</mark>', '...', 40) as snippet,
                    d.description
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

            if allowed_prefixes is not None and "" not in allowed_prefixes:
                if not allowed_prefixes:
                    return []
                grant_clauses = []
                for i, prefix in enumerate(allowed_prefixes):
                    p_exact = f":gp_exact_{i}"
                    p_like = f":gp_like_{i}"
                    grant_clauses.append(f"(d.path = {p_exact} OR d.path LIKE {p_like})")
                    params[f"gp_exact_{i}"] = prefix
                    params[f"gp_like_{i}"] = f"{prefix}/%"
                sql += f" AND ({' OR '.join(grant_clauses)})"

            if date_from:
                sql += " AND d.updated_at >= :date_from"
                params["date_from"] = date_from.isoformat()

            if date_to:
                sql += " AND d.updated_at <= :date_to"
                params["date_to"] = date_to.isoformat()

            sql += " ORDER BY rank LIMIT :limit"

            rows = self.db.execute(text(sql), params).fetchall()
            return self._process_fts_results(rows, keywords)

        except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.ProgrammingError):
            # FTS5 table may not exist yet — fall back to LIKE search
            return self._fallback_like_search(query, limit, allowed_prefixes)

    def _process_fts_results(self, rows, keywords: Optional[list]) -> list[SearchResultResponse]:
        """Process FTS result rows into typed response objects.

        Both PostgreSQL and SQLite FTS queries SELECT the same column order:
        id, title, path, doc_type, keywords, repo_name, content_preview,
        updated_at, generation_count, rank, snippet, description.
        """
        import json

        results: list[SearchResultResponse] = []
        for row in rows:
            doc_id, title, path, doc_type, raw_keywords, repo_name = row[0], row[1], row[2], row[3], row[4], row[5]
            content_preview, updated_at, generation_count, rank, snippet = row[6], row[7], row[8], row[9], row[10]
            description = row[11] if len(row) > 11 else None

            # Keywords may come as JSON string (SQLite) or native list (PostgreSQL)
            doc_keywords = raw_keywords
            if isinstance(doc_keywords, str):
                try:
                    doc_keywords = json.loads(doc_keywords)
                except (json.JSONDecodeError, TypeError):
                    doc_keywords = []

            # Apply keyword filter in Python (simpler than SQL JSON filtering)
            if keywords:
                if not any(k in (doc_keywords or []) for k in keywords):
                    continue

            results.append(SearchResultResponse(
                id=doc_id,
                title=title,
                path=path,
                doc_type=doc_type or "",
                keywords=doc_keywords or [],
                description=description,
                repo_name=repo_name,
                content_preview=content_preview,
                updated_at=updated_at,
                generation_count=generation_count,
                rank=rank,
                snippet=snippet,
            ))
        return results

    def _fallback_like_search(
        self, query: str, limit: int, allowed_prefixes: Optional[list[str]]
    ) -> list[SearchResultResponse]:
        """Fallback to LIKE search when FTS is unavailable."""
        docs = self.search(query, limit, allowed_prefixes=allowed_prefixes)
        return [
            SearchResultResponse(
                id=d.id,
                title=d.title,
                path=d.path,
                doc_type=d.doc_type or "",
                keywords=d.keywords or [],
                repo_name=d.repo_name,
                content_preview=d.content_preview,
                updated_at=d.updated_at,
                generation_count=d.generation_count,
                rank=0.0,
                snippet=None,
            )
            for d in docs
        ]

    def get_recent(self, limit: int = 20, allowed_prefixes: Optional[list[str]] = None) -> List[Document]:
        """Get most recently updated active documents."""
        query = self._base_query()
        if allowed_prefixes is not None:
            grant_filter = self._grant_filter(allowed_prefixes)
            if grant_filter is not None:
                query = query.filter(grant_filter)
        return query.order_by(Document.updated_at.desc()).limit(limit).all()

    # -- Embedding methods --------------------------------------------------

    def update_embedding(self, doc_id: str, embedding: list[float], model_name: str) -> None:
        """Store embedding vector and model name for a document.

        For PostgreSQL: writes to description_embedding (vector column) + embedding_model.
        For SQLite: only writes embedding_model (no vector column).
        """
        if is_postgresql():
            self.db.execute(
                text("""
                    UPDATE documents
                    SET description_embedding = :embedding::vector,
                        embedding_model = :model
                    WHERE id = :doc_id
                """),
                {"embedding": str(embedding), "model": model_name, "doc_id": doc_id},
            )
        else:
            # SQLite has no vector column — just track the model name
            doc = self.get_by_id(doc_id)
            doc.embedding_model = model_name
        self.db.flush()

    def search_by_vector(
        self,
        query_embedding: list[float],
        limit: int = 5,
        exclude_id: str | None = None,
        allowed_prefixes: list[str] | None = None,
    ) -> list[SimilarDocumentResponse]:
        """Find documents by cosine similarity. PostgreSQL only (pgvector)."""
        if not is_postgresql():
            return []

        try:
            sql = """
                SELECT d.id, d.title, d.path, d.description,
                       1 - (d.description_embedding <=> :embedding::vector) as similarity
                FROM documents d
                WHERE d.description_embedding IS NOT NULL
                AND d.deleted_at IS NULL
            """
            params: dict = {"embedding": str(query_embedding), "limit": limit}

            if exclude_id:
                sql += " AND d.id != :exclude_id"
                params["exclude_id"] = exclude_id

            if allowed_prefixes is not None and "" not in allowed_prefixes:
                if not allowed_prefixes:
                    return []
                grant_clauses = []
                for i, prefix in enumerate(allowed_prefixes):
                    grant_clauses.append(f"(d.path = :gp_exact_{i} OR d.path LIKE :gp_like_{i})")
                    params[f"gp_exact_{i}"] = prefix
                    params[f"gp_like_{i}"] = f"{prefix}/%"
                sql += f" AND ({' OR '.join(grant_clauses)})"

            sql += " ORDER BY d.description_embedding <=> :embedding::vector LIMIT :limit"

            rows = self.db.execute(text(sql), params).fetchall()
            return [
                SimilarDocumentResponse(
                    id=row[0],
                    title=row[1],
                    path=row[2],
                    description=row[3],
                    similarity_score=round(float(row[4]), 4) if row[4] else 0.0,
                )
                for row in rows
            ]
        except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.ProgrammingError):
            return []

    def get_unembedded_documents(self, model_name: str) -> list[Document]:
        """Get documents that need (re-)embedding — missing or wrong model."""
        return (
            self._base_query()
            .filter(
                Document.description.isnot(None),
                Document.description != "",
                (Document.embedding_model != model_name) | (Document.embedding_model.is_(None)),
            )
            .all()
        )

    def move_folder(self, source_path: str, target_path: str) -> int:
        """Move folder by updating path prefixes (active docs only)."""
        affected_docs = self._base_query().filter(
            (Document.path == source_path) |
            (Document.path.like(f"{source_path}/%"))
        ).all()

        for doc in affected_docs:
            if doc.path == source_path:
                doc.path = target_path
            else:
                relative_path = doc.path[len(source_path) + 1:]
                doc.path = f"{target_path}/{relative_path}"

        return len(affected_docs)
