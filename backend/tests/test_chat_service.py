"""Unit tests for ChatService — RAG pipeline for question answering.

Tests the service layer with mocked LiteLLM calls and a real in-memory
SQLite database. Covers configuration checks, search term extraction,
context building, and answer generation.
"""

from unittest.mock import patch, MagicMock

from app.services.chat_service import ChatService, _extract_search_terms
from app.schemas.document import DocumentCreate, AskResponse
from app.services.document_service import DocumentService


def _create_doc(db, title="Test Doc", content="# Test\n\nContent about architecture.", path="crate/test"):
    svc = DocumentService(db)
    doc, _ = svc.create_or_update_document(
        DocumentCreate(
            title=title,
            path=path,
            content=content,
            repo_url="https://github.com/org/repo",
            repo_name="repo",
            author_type="human",
        )
    )
    return doc


class TestExtractSearchTerms:
    """Keyword extraction from natural language questions."""

    def test_filters_stop_words(self):
        terms = _extract_search_terms("What is the architecture of the system?")
        assert "what" not in terms
        assert "the" not in terms
        assert "architecture" in terms

    def test_filters_short_words(self):
        terms = _extract_search_terms("Is it an OK API?")
        assert "is" not in terms
        assert "it" not in terms
        assert "an" not in terms

    def test_limits_to_four_terms(self):
        terms = _extract_search_terms(
            "authentication authorization database caching logging monitoring tracing"
        )
        assert len(terms) <= 4

    def test_strips_punctuation(self):
        terms = _extract_search_terms("What's the deployment pipeline?")
        assert any("deployment" in t for t in terms)

    def test_empty_question(self):
        assert _extract_search_terms("") == []


class TestChatServiceConfig:
    """Configuration detection for RAG chat."""

    def test_not_configured_by_default(self, db):
        assert ChatService.is_configured() is False

    @patch("app.services.chat_service.settings")
    def test_configured_with_model_and_key(self, mock_settings, db):
        mock_settings.chat_model = "gpt-4o-mini"
        mock_settings.chat_api_key = "sk-test"
        mock_settings.embedding_api_key = None
        assert ChatService.is_configured() is True

    @patch("app.services.chat_service.settings")
    def test_configured_with_embedding_key_fallback(self, mock_settings, db):
        mock_settings.chat_model = "gpt-4o-mini"
        mock_settings.chat_api_key = None
        mock_settings.embedding_api_key = "emb-key"
        assert ChatService.is_configured() is True


class TestAsk:
    """RAG question answering pipeline."""

    def test_returns_not_configured_message(self, db):
        svc = ChatService(db)
        result = svc.ask("What is architecture?")
        assert isinstance(result, AskResponse)
        assert "not configured" in result.answer.lower()
        assert result.sources == []

    @patch("app.services.chat_service.settings")
    def test_returns_no_docs_found(self, mock_settings, db):
        mock_settings.chat_model = "gpt-4o-mini"
        mock_settings.chat_api_key = "sk-test"
        mock_settings.chat_api_base = None
        mock_settings.embedding_model = None
        mock_settings.embedding_api_key = None

        svc = ChatService(db)
        result = svc.ask("completely unrelated gibberish xyz123")
        assert isinstance(result, AskResponse)
        assert "no relevant" in result.answer.lower()

    @patch("app.services.chat_service.settings")
    def test_returns_answer_with_sources(self, mock_settings, db):
        mock_settings.chat_model = "gpt-4o-mini"
        mock_settings.chat_api_key = "sk-test"
        mock_settings.chat_api_base = None
        mock_settings.embedding_model = None
        mock_settings.embedding_api_key = None

        # Create a doc with searchable content
        _create_doc(db, title="Architecture", content="The system uses microservices architecture with event-driven communication.")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "The system uses microservices."

        with patch("litellm.completion", return_value=mock_response):
            svc = ChatService(db)
            result = svc.ask("architecture")

        assert isinstance(result, AskResponse)
        assert result.answer == "The system uses microservices."
        assert len(result.sources) >= 1
        assert result.sources[0].title == "Architecture"
        assert result.model == "gpt-4o-mini"

    @patch("app.services.chat_service.settings")
    def test_returns_sources_on_llm_failure(self, mock_settings, db):
        mock_settings.chat_model = "gpt-4o-mini"
        mock_settings.chat_api_key = "sk-test"
        mock_settings.chat_api_base = None
        mock_settings.embedding_model = None
        mock_settings.embedding_api_key = None

        _create_doc(db, title="Deploy Guide", content="Deployment uses Docker containers with orchestration.")

        with patch("litellm.completion", side_effect=Exception("LLM down")):
            svc = ChatService(db)
            result = svc.ask("deployment")

        assert isinstance(result, AskResponse)
        assert "unable to generate" in result.answer.lower()
        # Sources should still be returned even when LLM fails
        assert len(result.sources) >= 1
