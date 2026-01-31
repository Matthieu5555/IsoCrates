"""Repository for folder metadata database operations."""

from sqlalchemy.orm import Session
from typing import List, Optional
from ..models.folder_metadata import FolderMetadata
from ..schemas.folder import FolderMetadataCreate, FolderMetadataUpdate


class FolderMetadataRepository:
    """Data access layer for folder metadata."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, folder_id: str, data: FolderMetadataCreate) -> FolderMetadata:
        """Create new folder metadata."""
        folder = FolderMetadata(
            id=folder_id,
            path=data.path,
            description=data.description,
            icon=data.icon,
            sort_order=data.sort_order
        )
        self.db.add(folder)
        self.db.commit()
        self.db.refresh(folder)
        return folder

    def get_by_id(self, folder_id: str) -> Optional[FolderMetadata]:
        """Get folder metadata by ID."""
        return self.db.query(FolderMetadata).filter(FolderMetadata.id == folder_id).first()

    def get_by_path(self, path: str) -> Optional[FolderMetadata]:
        """Get folder metadata by full path."""
        return self.db.query(FolderMetadata).filter(FolderMetadata.path == path).first()

    def get_all(self) -> List[FolderMetadata]:
        """Get all folder metadata."""
        return self.db.query(FolderMetadata).order_by(
            FolderMetadata.sort_order,
            FolderMetadata.path
        ).all()

    def update(self, folder_id: str, data: FolderMetadataUpdate) -> Optional[FolderMetadata]:
        """Update folder metadata."""
        folder = self.get_by_id(folder_id)
        if not folder:
            return None

        if data.description is not None:
            folder.description = data.description
        if data.icon is not None:
            folder.icon = data.icon
        if data.sort_order is not None:
            folder.sort_order = data.sort_order

        self.db.commit()
        self.db.refresh(folder)
        return folder

    def delete(self, folder_id: str) -> bool:
        """Delete folder metadata."""
        folder = self.get_by_id(folder_id)
        if not folder:
            return False

        self.db.delete(folder)
        self.db.commit()
        return True

    def cleanup_orphans(self, existing_paths: set) -> int:
        """Remove folder metadata for paths that no longer exist."""
        orphans = self.db.query(FolderMetadata).filter(
            FolderMetadata.path.notin_(existing_paths)
        ).all()

        count = len(orphans)
        for orphan in orphans:
            self.db.delete(orphan)

        if count > 0:
            self.db.commit()

        return count
