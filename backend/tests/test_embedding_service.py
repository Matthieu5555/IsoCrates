"""Unit tests for EmbeddingService — provider-agnostic embedding management.

Tests use a real in-memory SQLite database with mocked LiteLLM calls.
Covers single/batch embedding, document embedding, similarity search,
and reindexing flow.

All tests that check "not configured" behavior patch settings to ensure
isolation from any EMBEDDING_MODEL in the real environment.
"""

from unittest.mock import patch, MagicMock
import pytest

from app.services.embedding_service import EmbeddingService
from app.schemas.document import DocumentCreate
from app.services.document_service import DocumentService


def _create_doc(db, title="Test Doc", description="A document about testing.", path="crate/test"):
    svc = DocumentService(db)
    doc, _ = svc.create_or_update_document(
        DocumentCreate(
            title=title,
            path=path,
            content="# Test\n\nContent.",
            description=description,
            repo_url="https://github.com/org/repo",
            repo_name="repo",
            author_type="human",
        )
    )
    return doc


def _unconfigured_settings():
    """Return a patch that disables embedding configuration."""
    return patch("app.services.embedding_service.settings", embedding_model="", embedding_api_key=None, embedding_api_base=None, embedding_dimensions=None)


class TestIsConfigured:
    """Configuration detection."""

    def test_not_configured_when_no_model(self, db):
        with _unconfigured_settings():
            assert EmbeddingService.is_configured() is False

    @patch("app.services.embedding_service.settings")
    def test_configured_when_model_set(self, mock_settings, db):
        mock_settings.embedding_model = "text-embedding-3-small"
        assert EmbeddingService.is_configured() is True


class TestGenerateEmbedding:
    """Single-text embedding generation."""

    def test_returns_none_when_not_configured(self):
        with _unconfigured_settings():
            result = EmbeddingService.generate_embedding("hello")
        assert result is None

    @patch("app.services.embedding_service.settings")
    def test_returns_embedding_on_success(self, mock_settings):
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_api_key = "test-key"
        mock_settings.embedding_api_base = None
        mock_settings.embedding_dimensions = None

        fake_embedding = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.data = [{"embedding": fake_embedding}]

        with patch("litellm.embedding", return_value=mock_response) as mock_embed:
            result = EmbeddingService.generate_embedding("hello world")

        assert result == fake_embedding
        mock_embed.assert_called_once()

    @patch("app.services.embedding_service.settings")
    def test_returns_none_on_api_error(self, mock_settings):
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_api_key = "test-key"
        mock_settings.embedding_api_base = None
        mock_settings.embedding_dimensions = None

        with patch("litellm.embedding", side_effect=ValueError("API returned error")):
            result = EmbeddingService.generate_embedding("hello")
        assert result is None


class TestEmbedDocument:
    """Document-level embedding storage."""

    def test_returns_false_when_not_configured(self, db):
        with _unconfigured_settings():
            svc = EmbeddingService(db)
            assert svc.embed_document("any-id") is False

    @patch("app.services.embedding_service.settings")
    def test_returns_false_for_missing_doc(self, mock_settings, db):
        mock_settings.embedding_model = "text-embedding-3-small"
        svc = EmbeddingService(db)
        assert svc.embed_document("nonexistent") is False

    @patch("app.services.embedding_service.settings")
    def test_returns_false_for_doc_without_description(self, mock_settings, db):
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_api_key = None
        mock_settings.embedding_api_base = None
        mock_settings.embedding_dimensions = None
        doc = _create_doc(db, description=None)
        svc = EmbeddingService(db)
        assert svc.embed_document(doc.id) is False


class TestFindSimilar:
    """Semantic similarity search."""

    def test_returns_empty_when_not_configured(self, db):
        with _unconfigured_settings():
            svc = EmbeddingService(db)
            result = svc.find_similar("test query")
        assert result == []

    @patch("app.services.embedding_service.settings")
    def test_returns_empty_when_embedding_fails(self, mock_settings, db):
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_api_key = "key"
        mock_settings.embedding_api_base = None
        mock_settings.embedding_dimensions = None

        with patch.object(EmbeddingService, "generate_embedding", return_value=None):
            svc = EmbeddingService(db)
            result = svc.find_similar("test query")
        assert result == []


class TestGenerateEmbeddingsBatch:
    """Batch embedding generation."""

    def test_empty_input_returns_nones(self):
        with _unconfigured_settings():
            result = EmbeddingService.generate_embeddings_batch([])
        assert result == []

    def test_not_configured_returns_nones(self):
        with _unconfigured_settings():
            result = EmbeddingService.generate_embeddings_batch(["a", "b"])
        assert result == [None, None]

    @patch("app.services.embedding_service.settings")
    def test_batch_success(self, mock_settings):
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_api_key = "key"
        mock_settings.embedding_api_base = None
        mock_settings.embedding_dimensions = None

        fake_data = [
            {"embedding": [0.1, 0.2]},
            {"embedding": [0.3, 0.4]},
        ]
        mock_response = MagicMock()
        mock_response.data = fake_data

        with patch("litellm.embedding", return_value=mock_response):
            result = EmbeddingService.generate_embeddings_batch(["hello", "world"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]

    @patch("app.services.embedding_service.settings")
    def test_batch_falls_back_to_per_item(self, mock_settings):
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_api_key = "key"
        mock_settings.embedding_api_base = None
        mock_settings.embedding_dimensions = None

        with patch("litellm.embedding", side_effect=Exception("batch fail")):
            with patch.object(
                EmbeddingService,
                "generate_embedding",
                side_effect=[[0.1], [0.2]],
            ):
                result = EmbeddingService.generate_embeddings_batch(["a", "b"])
        assert result == [[0.1], [0.2]]
