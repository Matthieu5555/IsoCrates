"""
Deep module for managing document dependencies.

Hides all validation complexity:
- Both documents exist
- No circular dependencies
- No self-links
- No duplicates
"""

import re
import logging
from sqlalchemy.orm import Session
from typing import List, Optional, Set
from ..repositories.dependency_repository import DependencyRepository
from ..repositories.document_repository import DocumentRepository
from ..schemas.dependency import DependencyCreate, DependencyResponse
from ..models import Dependency
from ..exceptions import DocumentNotFoundError, CircularDependencyError, SelfDependencyError, ValidationError

logger = logging.getLogger(__name__)


class DependencyService:
    """
    Deep module for dependency management.

    Encapsulates all business logic for creating and managing document dependencies,
    including comprehensive validation that would otherwise be scattered across
    the codebase.
    """

    def __init__(self, db: Session):
        self.db = db
        self.dep_repo = DependencyRepository(db)
        self.doc_repo = DocumentRepository(db)

    def create_dependency(self, dependency: DependencyCreate) -> Dependency:
        """
        Create dependency with comprehensive validation.

        DEEP MODULE: Hides all validation complexity behind simple interface.
        Caller just provides from/to document IDs - all safety checks automatic.

        Validates:
        - Both documents exist (raises ValueError if not)
        - No self-links (raises ValueError)
        - No circular dependencies (raises ValueError)
        - Idempotent (returns existing if duplicate)

        Args:
            dependency: Dependency creation data

        Returns:
            Created or existing Dependency instance

        Raises:
            ValueError: If validation fails
        """
        # Validate source document exists
        source_doc = self.doc_repo.get_by_id(dependency.from_doc_id)
        if not source_doc:
            raise DocumentNotFoundError(dependency.from_doc_id)

        # Validate target document exists
        target_doc = self.doc_repo.get_by_id(dependency.to_doc_id)
        if not target_doc:
            raise DocumentNotFoundError(dependency.to_doc_id)

        # Validate no self-links
        if dependency.from_doc_id == dependency.to_doc_id:
            raise SelfDependencyError(dependency.from_doc_id)

        # Validate no circular dependencies for non-wikilink types.
        # Wikilinks are cross-references (A↔B is valid), not build dependencies.
        if dependency.link_type != "wikilink" and self._would_create_cycle(dependency.from_doc_id, dependency.to_doc_id):
            raise CircularDependencyError(dependency.from_doc_id, dependency.to_doc_id)

        # Check for existing dependency (idempotent)
        existing = self._find_existing(dependency.from_doc_id, dependency.to_doc_id)
        if existing:
            return existing

        # All validations passed - create dependency
        return self.dep_repo.create(dependency)

    def get_dependencies(self, doc_id: str) -> dict:
        """
        Get all dependencies for a document.

        Returns:
            dict with 'outgoing' and 'incoming' dependency lists
        """
        return self.dep_repo.get_by_document(doc_id)

    def get_all_dependencies(self) -> List[Dependency]:
        """Get all dependencies in the system (for graph visualization)."""
        return self.dep_repo.get_all()

    def delete_dependency(self, dependency_id: int) -> bool:
        """Delete a specific dependency by ID."""
        return self.dep_repo.delete(dependency_id)

    def delete_document_dependencies(self, doc_id: str) -> int:
        """
        Delete all dependencies for a document.

        Returns:
            Count of deleted dependencies
        """
        return self.dep_repo.delete_by_document(doc_id)

    def _find_existing(self, from_doc_id: str, to_doc_id: str) -> Optional[Dependency]:
        """
        Find existing dependency between two documents.

        Internal helper for idempotent create operations.
        """
        outgoing = self.dep_repo.get_by_source(from_doc_id)
        for dep in outgoing:
            if dep.to_doc_id == to_doc_id:
                return dep
        return None

    def _would_create_cycle(self, from_doc_id: str, to_doc_id: str) -> bool:
        """
        Check if adding this dependency would create a circular reference.

        Uses depth-first search to detect if there's already a path from
        to_doc_id back to from_doc_id. If so, adding from->to would create a cycle.

        Args:
            from_doc_id: Source document
            to_doc_id: Target document

        Returns:
            True if adding this dependency would create a cycle
        """
        # If there's already a path from target back to source, this would create a cycle
        return self._has_path(to_doc_id, from_doc_id, set())

    def replace_document_dependencies(self, doc_id: str, content: str) -> None:
        """
        Extract wikilinks from content and replace all outgoing dependencies.

        Deep module: Owns the full lifecycle of dependency extraction from document
        content. Deletes existing outgoing dependencies, parses wikilinks, resolves
        targets, and creates validated new dependencies.

        Args:
            doc_id: Source document ID
            content: Document markdown content containing [[wikilinks]]
        """
        # Delete existing outgoing dependencies for this document (single query)
        self.dep_repo.delete_outgoing(doc_id)

        # Extract and resolve wikilinks
        wikilink_targets = self._extract_wikilinks(content)

        for target in wikilink_targets:
            target_doc_id = self._resolve_wikilink(target)
            if target_doc_id and target_doc_id != doc_id:
                dependency = DependencyCreate(
                    from_doc_id=doc_id,
                    to_doc_id=target_doc_id,
                    link_type="wikilink",
                    link_text=target
                )
                try:
                    self.create_dependency(dependency)
                except (DocumentNotFoundError, CircularDependencyError, SelfDependencyError) as e:
                    logger.warning(
                        f"Skipped dependency from {doc_id} to {target_doc_id}: {e}",
                        extra={'from_doc_id': doc_id, 'to_doc_id': target_doc_id}
                    )

    def _extract_wikilinks(self, content: str) -> Set[str]:
        """Extract all wikilink targets from markdown content."""
        pattern = r'\[\[([^\]]+)\]\]'
        matches = re.findall(pattern, content)
        return set(matches)

    def _resolve_wikilink(self, target: str) -> Optional[str]:
        """Resolve a wikilink target to a document ID.

        Uses exact title match, then case-insensitive title match, then
        repo_name match. Partial/fuzzy matching was removed because it
        created false-positive dependencies to unrelated documents.
        """
        from sqlalchemy import func
        from ..models import Document

        active = Document.deleted_at.is_(None)

        # Stage 1: Exact title match
        doc = self.db.query(Document).filter(active, Document.title == target).first()
        if doc:
            return doc.id

        # Stage 2: Case-insensitive title match
        doc = self.db.query(Document).filter(
            active, func.lower(Document.title) == target.lower()
        ).first()
        if doc:
            return doc.id

        # Stage 3: Exact repo_name match (wikilinks often reference repo names)
        doc = self.db.query(Document).filter(
            active, Document.repo_name == target
        ).first()
        if doc:
            return doc.id

        # Stage 4: Case-insensitive repo_name match
        doc = self.db.query(Document).filter(
            active, func.lower(Document.repo_name) == target.lower()
        ).first()
        if doc:
            return doc.id

        return None

    def update_wikilinks_on_move(self, doc_id: str, old_identifier: str, new_identifier: str) -> int:
        """Update wikilink text in all documents that reference the moved document.

        Finds all incoming dependencies (other docs linking to this one), replaces
        [[old_identifier]] with [[new_identifier]] in their content, creates a
        system version for each update, and refreshes their dependency graphs.

        Returns the count of documents updated.
        """
        if old_identifier == new_identifier:
            return 0

        from ..schemas.version import VersionCreate
        from ..repositories.version_repository import VersionRepository
        from ..services.content_utils import generate_content_preview

        version_repo = VersionRepository(self.db)
        deps = self.dep_repo.get_by_document(doc_id)
        incoming = deps.get("incoming", [])

        updated_count = 0
        for dep in incoming:
            referring_doc = self.doc_repo.get_by_id(dep.from_doc_id)
            if not referring_doc:
                continue

            old_link = f"[[{old_identifier}]]"
            new_link = f"[[{new_identifier}]]"
            if old_link not in referring_doc.content:
                continue

            referring_doc.content = referring_doc.content.replace(old_link, new_link)
            referring_doc.content_preview = generate_content_preview(referring_doc.content)

            version = VersionCreate(
                doc_id=referring_doc.id,
                content=referring_doc.content,
                author_type="system",
                author_metadata={"reason": "wikilink_update", "moved_doc": doc_id},
            )
            version_repo.create(version)
            self.replace_document_dependencies(referring_doc.id, referring_doc.content)
            updated_count += 1

        if updated_count > 0:
            self.db.commit()

        return updated_count

    def get_broken_links(self, doc_id: str) -> list[dict]:
        """Check all wikilinks in a document and report their resolution status.

        Returns a list of dicts: [{target, resolved, resolved_doc_id}].
        An empty list means no wikilinks (not an error).
        """
        doc = self.doc_repo.get_by_id(doc_id)
        if not doc:
            return []

        targets = self._extract_wikilinks(doc.content)
        results = []
        for target in sorted(targets):
            resolved_id = self._resolve_wikilink(target)
            results.append({
                "target": target,
                "resolved": resolved_id is not None,
                "resolved_doc_id": resolved_id,
            })
        return results

    def _has_path(self, start: str, target: str, visited: Set[str]) -> bool:
        """
        DFS to check if there's a path from start to target.

        Internal helper for cycle detection.

        Args:
            start: Starting document ID
            target: Target document ID to reach
            visited: Set of already-visited nodes (prevents infinite loops)

        Returns:
            True if path exists from start to target
        """
        if start == target:
            return True

        if start in visited:
            return False

        visited.add(start)

        # Get all outgoing dependencies from current node
        outgoing = self.dep_repo.get_by_source(start)
        for dep in outgoing:
            if self._has_path(dep.to_doc_id, target, visited):
                return True

        return False
