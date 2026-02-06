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

    def get_all(self) -> List[Dependency]:
        """Get all dependencies in the system (for graph view).
        Excludes dependencies involving soft-deleted documents."""
        active_ids = (
            self.db.query(Document.id)
            .filter(Document.deleted_at.is_(None))
            .subquery()
        )
        return (
            self.db.query(Dependency)
            .filter(Dependency.from_doc_id.in_(active_ids))
            .filter(Dependency.to_doc_id.in_(active_ids))
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
