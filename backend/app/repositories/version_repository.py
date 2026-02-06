"""Version repository for database operations."""

from typing import List, Optional
from datetime import datetime, timezone
import hashlib
from ..models import Version
from ..schemas.version import VersionCreate
from ..exceptions import VersionNotFoundError
from .base import BaseRepository


class VersionRepository(BaseRepository[Version]):
    """Repository for version CRUD operations."""

    model_class = Version
    id_column = "version_id"
    not_found_error = VersionNotFoundError

    def create(self, version: VersionCreate) -> Version:
        """Create a new version."""
        # Generate version ID: {doc_id}-{timestamp}
        timestamp = datetime.now(timezone.utc).isoformat().replace(':', '-').replace('.', '-')
        version_id = f"{version.doc_id}-{timestamp}"

        # Calculate content hash (SHA256)
        content_hash = hashlib.sha256(version.content.encode()).hexdigest()

        db_version = Version(
            version_id=version_id,
            doc_id=version.doc_id,
            content=version.content,
            content_hash=content_hash,
            author_type=version.author_type,
            author_metadata=version.author_metadata
        )
        self.db.add(db_version)
        self.db.flush()
        self.db.refresh(db_version)
        return db_version

    # get_by_id and get_by_id_optional are inherited from BaseRepository
    # with id_column="version_id".

    def get_by_document(self, doc_id: str, skip: int = 0, limit: int = 50) -> List[Version]:
        """Get all versions for a document."""
        return self.db.query(Version).filter(
            Version.doc_id == doc_id
        ).order_by(Version.created_at.desc()).offset(skip).limit(limit).all()

    def get_latest(self, doc_id: str) -> Optional[Version]:
        """Get latest version for a document."""
        return self.db.query(Version).filter(
            Version.doc_id == doc_id
        ).order_by(Version.created_at.desc()).first()
