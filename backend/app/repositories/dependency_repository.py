"""Dependency repository for database operations."""

from typing import List
from ..models import Dependency, Document
from ..schemas.dependency import DependencyCreate, DocumentDependencies, DependencyResponse
from .base import BaseRepository


class DependencyRepository(BaseRepository[Dependency]):
    """Repository for dependency CRUD operations."""

    model_class = Dependency

    def create(self, dependency: DependencyCreate) -> Dependency:
        """Create a new dependency."""
        db_dependency = Dependency(
            from_doc_id=dependency.from_doc_id,
            to_doc_id=dependency.to_doc_id,
            link_type=dependency.link_type,
            link_text=dependency.link_text,
            section=dependency.section
        )
        self.db.add(db_dependency)
        self.db.flush()
        self.db.refresh(db_dependency)
        return db_dependency

    def get_by_document(self, doc_id: str) -> DocumentDependencies:
        """Get all dependencies for a document (incoming and outgoing)."""
        outgoing = self.db.query(Dependency).filter(Dependency.from_doc_id == doc_id).all()
        incoming = self.db.query(Dependency).filter(Dependency.to_doc_id == doc_id).all()

        return DocumentDependencies(
            outgoing=[DependencyResponse.model_validate(d) for d in outgoing],
            incoming=[DependencyResponse.model_validate(d) for d in incoming],
        )

    def get_all(self, allowed_prefixes: list[str] | None = None) -> List[Dependency]:
        """Get all dependencies in the system (for graph view).

        Excludes dependencies involving soft-deleted documents.
        When allowed_prefixes is provided, only includes dependencies where
        both endpoints are under an accessible path — filtering in SQL instead
        of loading all documents into Python.
        """
        from sqlalchemy import or_

        active_filter = Document.deleted_at.is_(None)

        if allowed_prefixes is not None and "" not in allowed_prefixes:
            if not allowed_prefixes:
                return []
            # Build path-prefix clauses once, reuse for both subqueries
            path_clauses = []
            for prefix in allowed_prefixes:
                path_clauses.append(Document.path == prefix)
                path_clauses.append(Document.path.like(f"{prefix}/%"))
            grant_filter = or_(*path_clauses)

            accessible_ids = (
                self.db.query(Document.id)
                .filter(active_filter, grant_filter)
                .subquery()
            )
        else:
            accessible_ids = (
                self.db.query(Document.id)
                .filter(active_filter)
                .subquery()
            )

        return (
            self.db.query(Dependency)
            .filter(Dependency.from_doc_id.in_(accessible_ids))
            .filter(Dependency.to_doc_id.in_(accessible_ids))
            .all()
        )

    def get_by_source(self, doc_id: str) -> List[Dependency]:
        """Get all outgoing dependencies from a document."""
        return self.db.query(Dependency).filter(Dependency.from_doc_id == doc_id).all()

    def delete(self, dependency_id: int) -> bool:
        """Delete a specific dependency by ID."""
        dependency = self.db.query(Dependency).filter(Dependency.id == dependency_id).first()
        if dependency:
            self.db.delete(dependency)
            return True
        return False

    def delete_by_document(self, doc_id: str) -> int:
        """Delete all dependencies for a document (both directions)."""
        count = self.db.query(Dependency).filter(
            (Dependency.from_doc_id == doc_id) | (Dependency.to_doc_id == doc_id)
        ).delete()
        return count

    def delete_outgoing(self, doc_id: str) -> int:
        """Delete all outgoing dependencies from a document."""
        count = self.db.query(Dependency).filter(
            Dependency.from_doc_id == doc_id
        ).delete()
        return count
