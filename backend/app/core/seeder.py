"""Seed initial documents on first startup.

Loads a JSON fixture of IsoCrates documentation into an empty database
so new users immediately see what the system does and what the agent
can generate.  Idempotent: skips if any documents already exist.
"""

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "seed_documents.json"


def seed_initial_documents(db: Session) -> int:
    """Load seed documents if the database is empty.

    Args:
        db: An open SQLAlchemy session.

    Returns:
        Number of documents seeded (0 if skipped).
    """
    from ..models.document import Document
    from ..services.document_service import DocumentService
    from ..schemas.document import DocumentCreate

    existing = db.query(Document).count()
    if existing > 0:
        logger.debug("Database has %d documents, skipping seed", existing)
        return 0

    if not _FIXTURE_PATH.exists():
        logger.debug("No seed fixture at %s", _FIXTURE_PATH)
        return 0

    try:
        with open(_FIXTURE_PATH) as f:
            fixture = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read seed fixture: %s", e)
        return 0

    documents = fixture.get("documents", [])
    if not documents:
        return 0

    service = DocumentService(db)
    seeded = 0

    for doc_data in documents:
        try:
            doc_create = DocumentCreate(**doc_data)
            service.create_or_update_document(doc_create, commit=False)
            seeded += 1
        except Exception as e:
            logger.warning("Failed to seed '%s': %s", doc_data.get("title", "?"), e)

    if seeded:
        db.commit()
        logger.info("Seeded %d documents from fixture", seeded)

        # Index seed documents for semantic search (no-op if embeddings not configured)
        from ..services.embedding_service import EmbeddingService
        embedding_svc = EmbeddingService(db)
        if embedding_svc.is_configured():
            indexed = embedding_svc.reindex_all()
            logger.info("Indexed %d seed documents", indexed)

    return seeded
