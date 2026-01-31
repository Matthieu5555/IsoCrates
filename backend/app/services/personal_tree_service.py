"""Service for personal tree operations: folders, document references, tree building."""

import logging
from typing import List, Optional, Dict

from sqlalchemy.orm import Session

from ..repositories.personal_tree_repository import PersonalTreeRepository
from ..repositories.document_repository import DocumentRepository
from ..models.personal import PersonalFolder, PersonalDocumentRef
from ..schemas.personal import PersonalTreeNode
from ..exceptions import ValidationError

logger = logging.getLogger(__name__)


class PersonalTreeService:
    """Business logic for the personal tree.

    Public methods:
        get_tree         -- full personal tree as PersonalTreeNode list
        create_folder    -- create a personal folder
        delete_folder    -- delete a personal folder (cascade deletes children + refs)
        move_folder      -- move folder to a new parent
        add_document_ref -- add a reference to an org document in a personal folder
        remove_ref       -- remove a document reference
        move_ref         -- move a ref to a different folder
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = PersonalTreeRepository(db)
        self.doc_repo = DocumentRepository(db)

    def get_tree(self, user_id: str = "default") -> List[PersonalTreeNode]:
        """Build the full personal tree for a user."""
        folders = self.repo.get_folders_by_user(user_id)
        refs = self.repo.get_refs_by_user(user_id)

        # Load document titles for refs
        doc_ids = {r.document_id for r in refs}
        doc_map: Dict[str, str] = {}
        for doc_id in doc_ids:
            doc = self.doc_repo.get_by_id(doc_id)
            if doc:
                doc_map[doc_id] = doc.title or doc_id

        # Index refs by folder_id
        refs_by_folder: Dict[str, List[PersonalDocumentRef]] = {}
        for ref in refs:
            refs_by_folder.setdefault(ref.folder_id, []).append(ref)

        # Index folders by parent_id
        children_by_parent: Dict[Optional[str], List[PersonalFolder]] = {}
        for folder in folders:
            children_by_parent.setdefault(folder.parent_id, []).append(folder)

        # Recursive build
        def build_children(parent_id: Optional[str]) -> List[PersonalTreeNode]:
            nodes: List[PersonalTreeNode] = []
            for folder in children_by_parent.get(parent_id, []):
                child_nodes = build_children(folder.folder_id)

                # Add document refs as leaf nodes
                for ref in refs_by_folder.get(folder.folder_id, []):
                    title = doc_map.get(ref.document_id, ref.document_id)
                    child_nodes.append(PersonalTreeNode(
                        id=ref.ref_id,
                        name=title,
                        type="document",
                        document_id=ref.document_id,
                        ref_id=ref.ref_id,
                    ))

                nodes.append(PersonalTreeNode(
                    id=folder.folder_id,
                    name=folder.name,
                    type="folder",
                    folder_id=folder.folder_id,
                    children=child_nodes,
                ))
            return nodes

        return build_children(None)

    def create_folder(self, user_id: str, name: str, parent_id: Optional[str] = None) -> PersonalFolder:
        """Create a personal folder. Validates parent exists if provided."""
        if parent_id:
            parent = self.repo.get_folder(parent_id)
            if not parent:
                raise ValidationError(f"Parent folder not found: {parent_id}", field="parent_id")
            if parent.user_id != user_id:
                raise ValidationError("Parent folder belongs to a different user", field="parent_id")

        return self.repo.create_folder(user_id, name, parent_id)

    def delete_folder(self, folder_id: str) -> bool:
        """Delete a personal folder. CASCADE removes children and refs."""
        folder = self.repo.get_folder(folder_id)
        if not folder:
            raise ValidationError(f"Folder not found: {folder_id}", field="folder_id")
        return self.repo.delete_folder(folder_id)

    def move_folder(self, folder_id: str, new_parent_id: Optional[str]) -> PersonalFolder:
        """Move a personal folder to a new parent (or root if None)."""
        folder = self.repo.get_folder(folder_id)
        if not folder:
            raise ValidationError(f"Folder not found: {folder_id}", field="folder_id")

        if new_parent_id:
            parent = self.repo.get_folder(new_parent_id)
            if not parent:
                raise ValidationError(f"Target parent not found: {new_parent_id}", field="parent_id")
            # Prevent moving into own descendant
            if self._is_descendant(folder_id, new_parent_id):
                raise ValidationError("Cannot move folder into its own descendant", field="parent_id")

        result = self.repo.move_folder(folder_id, new_parent_id)
        if not result:
            raise ValidationError(f"Move failed for folder: {folder_id}")
        return result

    def add_document_ref(self, user_id: str, folder_id: str, document_id: str) -> PersonalDocumentRef:
        """Add a reference to an org document in a personal folder. Idempotent."""
        # Validate folder exists and belongs to user
        folder = self.repo.get_folder(folder_id)
        if not folder:
            raise ValidationError(f"Folder not found: {folder_id}", field="folder_id")
        if folder.user_id != user_id:
            raise ValidationError("Folder belongs to a different user", field="folder_id")

        # Validate document exists
        doc = self.doc_repo.get_by_id(document_id)
        if not doc:
            raise ValidationError(f"Document not found: {document_id}", field="document_id")

        # Idempotent: return existing if already referenced
        existing = self.repo.find_existing_ref(user_id, folder_id, document_id)
        if existing:
            return existing

        return self.repo.create_ref(user_id, folder_id, document_id)

    def remove_ref(self, ref_id: str) -> bool:
        """Remove a document reference."""
        ref = self.repo.get_ref(ref_id)
        if not ref:
            raise ValidationError(f"Reference not found: {ref_id}", field="ref_id")
        return self.repo.delete_ref(ref_id)

    def move_ref(self, ref_id: str, target_folder_id: str) -> PersonalDocumentRef:
        """Move a document reference to a different folder."""
        ref = self.repo.get_ref(ref_id)
        if not ref:
            raise ValidationError(f"Reference not found: {ref_id}", field="ref_id")

        folder = self.repo.get_folder(target_folder_id)
        if not folder:
            raise ValidationError(f"Target folder not found: {target_folder_id}", field="folder_id")

        result = self.repo.move_ref(ref_id, target_folder_id)
        if not result:
            raise ValidationError(f"Move failed for ref: {ref_id}")
        return result

    def _is_descendant(self, ancestor_id: str, candidate_id: str) -> bool:
        """Check if candidate_id is a descendant of ancestor_id."""
        if ancestor_id == candidate_id:
            return True
        children = self.repo.get_children(ancestor_id)
        for child in children:
            if self._is_descendant(child.folder_id, candidate_id):
                return True
        return False
