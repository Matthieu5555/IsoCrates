"""Base repository with shared get-by-ID patterns.

Eliminates duplicated __init__, get_by_id, and get_by_id_optional logic
across repositories.  Subclasses specify model_class, id_column, and
not_found_error; the base provides the common implementations.

Override _base_query() to apply default filters (e.g., soft-delete
exclusion in DocumentRepository).
"""

from typing import TypeVar, Generic, Optional, Type
from sqlalchemy.orm import Session, Query

from ..database import Base
from ..exceptions import IsoException

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Shared repository logic for SQLAlchemy models.

    Class variables to set in subclasses:
        model_class:     The SQLAlchemy model (e.g., Document)
        id_column:       Name of the primary-key column (default "id")
        not_found_error: Exception class to raise from get_by_id
    """

    model_class: Type[ModelT]
    id_column: str = "id"
    not_found_error: Type[IsoException]

    def __init__(self, db: Session):
        self.db = db

    def _base_query(self) -> Query:
        """Base query for get_by_id / get_by_id_optional.

        Override in subclasses to apply default filters
        (e.g., soft-delete exclusion).
        """
        return self.db.query(self.model_class)

    def get_by_id(self, entity_id: str) -> ModelT:
        """Get entity by primary key. Raises not_found_error if missing."""
        col = getattr(self.model_class, self.id_column)
        entity = self._base_query().filter(col == entity_id).first()
        if not entity:
            raise self.not_found_error(entity_id)
        return entity

    def get_by_id_optional(self, entity_id: str) -> Optional[ModelT]:
        """Get entity by primary key, or None if not found."""
        col = getattr(self.model_class, self.id_column)
        return self._base_query().filter(col == entity_id).first()
