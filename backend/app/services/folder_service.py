"""Deep module for all folder operations: CRUD, move, delete, and tree building.

Absorbs logic previously spread across FolderService, FolderOpsService, and TreeService.
The public interface is intentionally narrow -- callers interact with high-level operations
and never manage ancestor metadata, path validation, or tree construction themselves.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from ..models import Document
from ..models.folder_metadata import FolderMetadata
from ..repositories.document_repository import DocumentRepository
from ..repositories.folder_repository import FolderMetadataRepository
from ..schemas.folder import (
    FolderMetadataCreate,
    FolderMetadataUpdate,
    FolderOperationResponse,
    TreeNode,
)

# Upper bound on documents loaded for tree building.
# Increase if the tree is truncated; decrease if memory is a concern.
TREE_DOCUMENT_LIMIT = 1000
UNCATEGORIZED_FOLDER = "Uncategorized"

logger = logging.getLogger(__name__)


class FolderService:
    """All folder and tree operations behind a simple interface.

    Public methods:
        create_folder   -- idempotent; auto-creates ancestor metadata
        get_folder      -- lookup by id
        get_folder_by_path
        list_folders    -- optional path prefix filter
        update_folder   -- description / icon / sort_order
        delete_folder   -- remove folder (move_up or delete_all); idempotent
        move_folder     -- relocate subtree; ensures target ancestors
        get_tree        -- full navigation tree as TreeNode list
        cleanup_orphans -- remove metadata with no documents
    """

    def __init__(self, db: Session):
        self.db = db
        self.folder_repo = FolderMetadataRepository(db)
        self.doc_repo = DocumentRepository(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_folder(self, data: FolderMetadataCreate) -> FolderMetadata:
        """Create a folder. Idempotent: returns existing record if path is taken.

        Automatically creates metadata records for every ancestor path so that
        deleting a leaf folder never causes its parents to vanish from the tree.
        """
        folder_id = self._generate_folder_id(data.path)

        existing = self.folder_repo.get_by_id_optional(folder_id)
        if existing:
            return existing

        self._ensure_ancestors(data.path)
        result = self.folder_repo.create(folder_id, data)
        self.db.commit()
        return result

    def get_folder(self, folder_id: str) -> Optional[FolderMetadata]:
        return self.folder_repo.get_by_id_optional(folder_id)

    def get_folder_by_path(self, path: str) -> Optional[FolderMetadata]:
        return self.folder_repo.get_by_path(path)

    def list_folders(self, path_prefix: Optional[str] = None) -> List[FolderMetadata]:
        if path_prefix:
            return self.db.query(FolderMetadata).filter(
                (FolderMetadata.path == path_prefix)
                | (FolderMetadata.path.like(f"{path_prefix}/%"))
            ).order_by(FolderMetadata.sort_order, FolderMetadata.path).all()
        return self.folder_repo.get_all()

    def update_folder(
        self, folder_id: str, data: FolderMetadataUpdate
    ) -> Optional[FolderMetadata]:
        result = self.folder_repo.update(folder_id, data)
        self.db.commit()
        return result

    def delete_folder(self, folder_path: str, action: str = "move_up") -> FolderOperationResponse:
        """Delete a folder. Idempotent: succeeds with zero affected if path is missing.

        action='move_up'   -- contents are re-parented to the parent folder.
        action='delete_all' -- folder and all descendants are permanently removed.
        """
        if not self._path_exists(folder_path):
            return FolderOperationResponse(
                affected_documents=0,
                folder_path=folder_path,
                tree=self._tree_as_dicts(),
            )

        if action == "delete_all":
            return self._delete_folder_and_contents(folder_path)
        return self._delete_folder_move_up(folder_path)

    def move_folder(self, source_path: str, target_path: str) -> FolderOperationResponse:
        """Move a folder subtree to a new location.

        Validates constraints, moves all documents and metadata, ensures ancestor
        metadata at the target, and returns the refreshed tree.
        """
        if target_path == source_path:
            raise ValueError("Source and target paths are the same")
        if target_path.startswith(f"{source_path}/"):
            raise ValueError("Cannot move folder into its own descendant")
        if not self._path_exists(source_path):
            raise ValueError(f"Path '{source_path}' does not exist")
        if self._has_documents_at(target_path):
            raise ValueError(f"A folder already exists at path '{target_path}'")

        affected_count = self.doc_repo.move_folder(source_path, target_path)

        # Re-path folder metadata
        folder_meta = self.db.query(FolderMetadata).filter(
            (FolderMetadata.path == source_path)
            | (FolderMetadata.path.like(f"{source_path}/%"))
        ).all()

        for fm in folder_meta:
            if fm.path == source_path:
                fm.path = target_path
            else:
                relative = fm.path[len(source_path) + 1:]
                fm.path = f"{target_path}/{relative}"

        self._ensure_ancestors(target_path)
        self.db.commit()

        return FolderOperationResponse(
            affected_documents=affected_count,
            folder_path=target_path,
            old_path=source_path,
            new_path=target_path,
            tree=self._tree_as_dicts(),
        )

    def get_tree(self, allowed_prefixes: Optional[List[str]] = None) -> List[TreeNode]:
        """Build the hierarchical navigation tree, optionally scoped to allowed prefixes."""
        return self._build_tree(allowed_prefixes=allowed_prefixes)

    def cleanup_orphans(self) -> int:
        """Remove folder metadata for paths that no longer contain any documents."""
        docs = self.db.query(Document).filter(Document.deleted_at.is_(None)).all()

        active_paths: set[str] = set()
        for doc in docs:
            if doc.path:
                parts = doc.path.split("/")
                for i in range(1, len(parts) + 1):
                    active_paths.add("/".join(parts[:i]))

        count = self.folder_repo.cleanup_orphans(active_paths)
        if count > 0:
            self.db.commit()
        return count

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_folder_id(self, path: str) -> str:
        """Deterministic folder ID from path."""
        # 12 hex chars = 48 bits, matching DOC_ID_PATH_HASH_LENGTH in document_service.py.
        # Changing this would break existing folder IDs in the database.
        path_hash = hashlib.sha256(path.encode()).hexdigest()[:12]
        return f"folder-{path_hash}"

    def _ensure_ancestors(self, path: str) -> None:
        """Create FolderMetadata for every ancestor of *path* that lacks one.

        For path 'a/b/c' this creates records for 'a' and 'a/b' (but not 'a/b/c').
        """
        segments = path.split("/")
        for i in range(1, len(segments)):
            ancestor_path = "/".join(segments[:i])
            ancestor_id = self._generate_folder_id(ancestor_path)
            if not self.folder_repo.get_by_id_optional(ancestor_id):
                self.folder_repo.create(
                    ancestor_id, FolderMetadataCreate(path=ancestor_path)
                )

    def _is_uncategorized(self, path: str) -> bool:
        return path == UNCATEGORIZED_FOLDER

    def _doc_path_filter(self, path: str):
        """Return a SQLAlchemy filter matching documents at or under *path*.

        Handles the synthetic "Uncategorized" folder whose documents have
        path='' or path=NULL in the database.
        """
        if self._is_uncategorized(path):
            return (Document.path.is_(None)) | (Document.path == "")
        return (Document.path == path) | (Document.path.like(f"{path}/%"))

    def _path_exists(self, path: str) -> bool:
        """True if any active documents or folder metadata exist at or under *path*."""
        has_docs = (
            self.db.query(Document)
            .filter(Document.deleted_at.is_(None))
            .filter(self._doc_path_filter(path))
            .first()
            is not None
        )
        if has_docs:
            return True
        return (
            self.db.query(FolderMetadata)
            .filter(
                (FolderMetadata.path == path)
                | (FolderMetadata.path.like(f"{path}/%"))
            )
            .first()
            is not None
        )

    def _has_documents_at(self, path: str) -> bool:
        return (
            self.db.query(Document)
            .filter(Document.deleted_at.is_(None))
            .filter(Document.path == path)
            .first() is not None
        )

    # -- Deletion variants ------------------------------------------------

    def _delete_folder_and_contents(self, folder_path: str) -> FolderOperationResponse:
        """Delete folder and everything inside it (only active documents)."""
        docs = (
            self.db.query(Document)
            .filter(Document.deleted_at.is_(None))
            .filter(self._doc_path_filter(folder_path))
            .all()
        )
        affected_count = len(docs)
        now = datetime.now(timezone.utc)
        for doc in docs:
            doc.deleted_at = now

        # Only delete metadata for target and descendants, never ancestors
        metas = (
            self.db.query(FolderMetadata)
            .filter(
                (FolderMetadata.path == folder_path)
                | (FolderMetadata.path.like(f"{folder_path}/%"))
            )
            .all()
        )
        for folder_meta in metas:
            self.db.delete(folder_meta)

        self.db.commit()
        return FolderOperationResponse(
            affected_documents=affected_count,
            folder_path=folder_path,
            tree=self._tree_as_dicts(),
        )

    def _delete_folder_move_up(self, folder_path: str) -> FolderOperationResponse:
        """Delete folder but re-parent its contents to the parent folder."""
        parent_path = (
            "/".join(folder_path.split("/")[:-1]) if "/" in folder_path else ""
        )

        affected_count = 0

        if self._is_uncategorized(folder_path):
            # "Uncategorized" is virtual — documents already have empty path,
            # there is nowhere to move them up to. Just count them.
            docs = (
                self.db.query(Document)
                .filter(Document.deleted_at.is_(None))
                .filter(self._doc_path_filter(folder_path))
                .all()
            )
            affected_count = len(docs)
        else:
            # Move direct documents to parent
            docs = self.db.query(Document).filter(Document.deleted_at.is_(None)).filter(Document.path == folder_path).all()
            for doc in docs:
                doc.path = parent_path
                affected_count += 1

            # Move documents in subfolders: strip the deleted segment
            subdocs = (
                self.db.query(Document)
                .filter(Document.deleted_at.is_(None))
                .filter(Document.path.like(f"{folder_path}/%"))
                .all()
            )
            for doc in subdocs:
                remaining = doc.path[len(folder_path) + 1:]
                doc.path = f"{parent_path}/{remaining}" if parent_path else remaining
                affected_count += 1

        # Delete only this folder's metadata
        fm = (
            self.db.query(FolderMetadata)
            .filter(FolderMetadata.path == folder_path)
            .first()
        )
        if fm:
            self.db.delete(fm)

        # Re-parent subfolder metadata
        subfolder_meta = (
            self.db.query(FolderMetadata)
            .filter(FolderMetadata.path.like(f"{folder_path}/%"))
            .all()
        )
        for fm in subfolder_meta:
            remaining = fm.path[len(folder_path) + 1:]
            fm.path = f"{parent_path}/{remaining}" if parent_path else remaining

        self.db.commit()
        return FolderOperationResponse(
            affected_documents=affected_count,
            folder_path=folder_path,
            tree=self._tree_as_dicts(),
        )

    # -- Tree building ----------------------------------------------------

    def _tree_as_dicts(self) -> List[Dict[str, Any]]:
        return [node.dict() for node in self._build_tree()]

    def _build_tree(self, allowed_prefixes: Optional[List[str]] = None) -> List[TreeNode]:
        """Build hierarchical tree from documents and folder metadata.

        path format: "crate/folder/subfolder"
        First segment = crate (top-level, is_crate=True).

        When *allowed_prefixes* is provided, only documents under those path
        prefixes are loaded from the database.
        """
        documents = self.doc_repo.get_all(limit=TREE_DOCUMENT_LIMIT, allowed_prefixes=allowed_prefixes)
        folder_metadata_list = self.folder_repo.get_all()

        # Index folder metadata by path
        metadata_map: Dict[str, Dict] = {}
        for fm in folder_metadata_list:
            metadata_map[fm.path] = {
                "description": fm.description,
                "icon": fm.icon,
                "sort_order": fm.sort_order,
            }

        tree_dict: Dict = {}

        def ensure_path(path_segments: List[str]) -> Dict:
            """Ensure all segments exist in the tree, return the leaf node dict."""
            current_children = tree_dict
            node = None
            for seg in path_segments:
                if seg not in current_children:
                    current_children[seg] = {"_children": {}, "_docs": []}
                node = current_children[seg]
                current_children = node["_children"]
            return node

        for doc in documents:
            path = doc.path or UNCATEGORIZED_FOLDER
            node = ensure_path(path.split("/"))
            node["_docs"].append(doc)

        for fm_path in metadata_map:
            ensure_path(fm_path.split("/"))

        return self._dict_to_tree(tree_dict, "", metadata_map, is_top_level=True)

    def _dict_to_tree(
        self,
        tree_dict: Dict,
        parent_path: str,
        metadata_map: Dict,
        is_top_level: bool = False,
    ) -> List[TreeNode]:
        """Recursively convert nested dict to TreeNode list."""
        nodes = []
        for name in sorted(tree_dict.keys()):
            if name.startswith("_"):
                continue

            node_data = tree_dict[name]
            full_path = f"{parent_path}/{name}" if parent_path else name
            metadata = metadata_map.get(full_path, {})

            folder_node = TreeNode(
                id=f"folder-{full_path}",
                name=name,
                type="folder",
                is_crate=is_top_level,
                path=full_path,
                children=[],
                description=metadata.get("description"),
                icon=metadata.get("icon"),
            )

            children_dict = node_data.get("_children", {})
            if children_dict:
                folder_node.children.extend(
                    self._dict_to_tree(
                        children_dict, full_path, metadata_map, is_top_level=False
                    )
                )

            docs = node_data.get("_docs", [])
            for doc in sorted(docs, key=lambda d: d.title or ""):
                display_name = (
                    doc.title if doc.title else f"{doc.repo_name} ({doc.doc_type})"
                )
                folder_node.children.append(
                    TreeNode(
                        id=doc.id,
                        name=display_name,
                        type="document",
                        path=doc.path,
                        doc_type=doc.doc_type,
                    )
                )

            nodes.append(folder_node)
        return nodes
