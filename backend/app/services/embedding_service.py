"""Embedding service for semantic search.

Provider-agnostic via LiteLLM — supports OpenAI, Cohere, Ollama, and any
OpenAI-compatible endpoint. Configure via EMBEDDING_MODEL env var.
"""

import logging
from sqlalchemy.orm import Session

from ..core.config import settings
from ..repositories.document_repository import DocumentRepository

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates and manages document description embeddings."""

    def __init__(self, db: Session):
        self.db = db
        self.doc_repo = DocumentRepository(db)

    @staticmethod
    def is_configured() -> bool:
        """Check if embedding is configured."""
        return bool(settings.embedding_model)

    @staticmethod
    def generate_embedding(text: str) -> list[float] | None:
        """Generate an embedding vector for the given text.

        Returns None if embedding is not configured or the call fails.
        """
        if not settings.embedding_model:
            return None

        try:
            import litellm

            kwargs: dict = {
                "model": settings.embedding_model,
                "input": [text],
            }
            if settings.embedding_api_key:
                kwargs["api_key"] = settings.embedding_api_key
            if settings.embedding_api_base:
                kwargs["api_base"] = settings.embedding_api_base
            if settings.embedding_dimensions:
                kwargs["dimensions"] = settings.embedding_dimensions

            response = litellm.embedding(**kwargs)
            return response.data[0]["embedding"]

        except Exception:
            logger.exception("Failed to generate embedding")
            return None

    def embed_document(self, doc_id: str) -> bool:
        """Generate and store embedding for a document's description.

        Returns True if embedding was stored, False otherwise.
        """
        if not self.is_configured():
            return False

        doc = self.doc_repo.get_by_id(doc_id)
        if not doc or not doc.description:
            return False

        embedding = self.generate_embedding(doc.description)
        if not embedding:
            return False

        self.doc_repo.update_embedding(doc_id, embedding, settings.embedding_model)
        self.db.commit()
        return True

    def find_similar(
        self,
        text: str,
        limit: int = 5,
        exclude_id: str | None = None,
        allowed_prefixes: list[str] | None = None,
    ) -> list:
        """Find documents with descriptions similar to the given text."""
        if not self.is_configured():
            return []

        embedding = self.generate_embedding(text)
        if not embedding:
            return []

        return self.doc_repo.search_by_vector(
            query_embedding=embedding,
            limit=limit,
            exclude_id=exclude_id,
            allowed_prefixes=allowed_prefixes,
        )

    def find_similar_to_doc(
        self,
        doc_id: str,
        limit: int = 5,
        allowed_prefixes: list[str] | None = None,
    ) -> list:
        """Find documents similar to an existing document."""
        doc = self.doc_repo.get_by_id(doc_id)
        if not doc or not doc.description:
            return []

        return self.find_similar(
            text=doc.description,
            limit=limit,
            exclude_id=doc_id,
            allowed_prefixes=allowed_prefixes,
        )

    @staticmethod
    def generate_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
        """Generate embeddings for multiple texts in a single API call.

        Returns a list parallel to *texts*; entries are None on failure.
        Falls back to per-item calls if the provider doesn't support batching.
        """
        if not settings.embedding_model or not texts:
            return [None] * len(texts)

        try:
            import litellm

            kwargs: dict = {
                "model": settings.embedding_model,
                "input": texts,
            }
            if settings.embedding_api_key:
                kwargs["api_key"] = settings.embedding_api_key
            if settings.embedding_api_base:
                kwargs["api_base"] = settings.embedding_api_base
            if settings.embedding_dimensions:
                kwargs["dimensions"] = settings.embedding_dimensions

            response = litellm.embedding(**kwargs)
            return [item["embedding"] for item in response.data]

        except Exception:
            logger.warning("Batch embedding failed, falling back to per-item calls")
            return [EmbeddingService.generate_embedding(t) for t in texts]

    # Maximum documents per embedding API call.
    # Keeps request payloads under provider limits and provides natural rate control.
    REINDEX_BATCH_SIZE = 20

    def reindex_all(self) -> int:
        """Re-embed all documents with descriptions. Returns count of documents embedded.

        Processes documents in batches to reduce API calls and respect rate limits.
        """
        if not self.is_configured():
            return 0

        docs = [d for d in self.doc_repo.get_unembedded_documents(settings.embedding_model) if d.description]
        count = 0

        for i in range(0, len(docs), self.REINDEX_BATCH_SIZE):
            batch = docs[i : i + self.REINDEX_BATCH_SIZE]
            texts = [doc.description for doc in batch]
            embeddings = self.generate_embeddings_batch(texts)

            for doc, embedding in zip(batch, embeddings):
                if embedding:
                    self.doc_repo.update_embedding(doc.id, embedding, settings.embedding_model)
                    count += 1

            # Commit per batch to avoid holding a long transaction
            if count > 0:
                self.db.commit()

        logger.info(f"Re-indexed {count} documents with model {settings.embedding_model}")
        return count
