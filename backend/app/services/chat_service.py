"""RAG chat service — answers questions using retrieved documentation.

Combines FTS + semantic search to find relevant documents, then sends
the context to an LLM via LiteLLM for answer generation.
"""

import logging
import re

from sqlalchemy.orm import Session

from ..core.config import settings
from ..repositories.document_repository import DocumentRepository
from ..schemas.document import AskResponse, ChatSource
from .embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

# Common stop words to strip from natural language questions for FTS
_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could this that these those "
    "i me my we our you your he him his she her it its they them their "
    "what which who whom how where when why and or not no nor but if "
    "then so than too very just about above after again all also any "
    "because before between both by down during each for from in into "
    "of on once only other out over own same some such up with".split()
)


def _extract_search_terms(question: str) -> list[str]:
    """Extract meaningful keywords from a natural language question for FTS."""
    words = re.sub(r'[^\w\s]', '', question.lower()).split()
    return [w for w in words if w not in _STOP_WORDS and len(w) > 2][:4]


SYSTEM_PROMPT = (
    "You are a documentation assistant for IsoCrates, a technical documentation platform. "
    "Answer the user's question based ONLY on the provided documentation excerpts. "
    "Cite document titles in [[double brackets]] when referencing them. "
    "If the documentation does not cover the question, say so clearly. "
    "Keep answers concise and factual."
)


class ChatService:
    """Answers questions by retrieving relevant docs and prompting an LLM."""

    def __init__(self, db: Session):
        self.db = db
        self.doc_repo = DocumentRepository(db)
        self.embedding_svc = EmbeddingService(db)

    @staticmethod
    def is_configured() -> bool:
        """Check if chat is configured (needs a model and API key)."""
        api_key = settings.chat_api_key or settings.embedding_api_key
        return bool(settings.chat_model and api_key)

    def ask(
        self,
        question: str,
        top_k: int = 5,
        allowed_prefixes: list[str] | None = None,
    ) -> AskResponse:
        """Answer a question using RAG.

        1. Retrieve relevant docs via FTS + semantic search
        2. Build context from top results
        3. Call LLM with context + question
        4. Return answer with source citations

        Returns:
            {"answer": str, "sources": [{"title", "id", "path"}], "model": str}
        """
        if not self.is_configured():
            return AskResponse(
                answer="Chat is not configured. Set CHAT_MODEL and either CHAT_API_KEY or EMBEDDING_API_KEY.",
                sources=[],
                model="",
            )

        # --- Retrieval ---
        docs_by_id: dict[str, dict] = {}

        def _add_doc(doc):
            if doc.id not in docs_by_id:
                docs_by_id[doc.id] = {
                    "id": doc.id,
                    "title": doc.title,
                    "path": doc.path,
                    "content": doc.content[:3000],
                    "description": doc.description or "",
                }

        # Semantic search first (handles natural language well)
        if self.embedding_svc.is_configured():
            try:
                similar = self.embedding_svc.find_similar(
                    text=question,
                    limit=top_k,
                    allowed_prefixes=allowed_prefixes,
                )
                for result in similar:
                    doc_id = result.id if hasattr(result, 'id') else result.get("id", "")
                    if doc_id and doc_id not in docs_by_id:
                        doc = self.doc_repo.get_by_id(doc_id)
                        if doc:
                            _add_doc(doc)
            except (ValueError, RuntimeError, ConnectionError, OSError) as e:
                logger.warning("Semantic search failed, falling back to FTS only: %s", e)

        # FTS search with individual keywords (OR-style: search each term separately)
        terms = _extract_search_terms(question)
        for term in terms:
            if len(docs_by_id) >= top_k:
                break
            try:
                fts_results = self.doc_repo.search_fts(
                    query=term,
                    limit=top_k,
                    allowed_prefixes=allowed_prefixes,
                )
                for result in fts_results:
                    if result.id not in docs_by_id:
                        doc = self.doc_repo.get_by_id(result.id)
                        if doc:
                            _add_doc(doc)
            except (ValueError, RuntimeError, OSError) as e:
                logger.warning("FTS search failed for term %r: %s", term, e)
                continue

        # Limit to top_k total
        context_docs = list(docs_by_id.values())[:top_k]

        if not context_docs:
            return AskResponse(
                answer="No relevant documentation found for this question.",
                sources=[],
                model=settings.chat_model,
            )

        # --- Build context ---
        context_parts = []
        for i, doc in enumerate(context_docs, 1):
            context_parts.append(
                f"--- Document {i}: {doc['title']} ---\n"
                f"Path: {doc['path']}\n"
                f"{doc['content']}\n"
            )
        context_text = "\n".join(context_parts)

        # --- LLM call ---
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Documentation context:\n\n{context_text}\n\n"
                    f"Question: {question}"
                ),
            },
        ]

        try:
            import litellm

            chat_kwargs: dict = {
                "model": settings.chat_model,
                "api_key": settings.chat_api_key or settings.embedding_api_key,
                "messages": messages,
                "max_tokens": 1024,
                "temperature": 0.3,
                "timeout": 30,
            }
            if settings.chat_api_base:
                chat_kwargs["api_base"] = settings.chat_api_base

            response = litellm.completion(**chat_kwargs)
            answer = response.choices[0].message.content
        except Exception as e:
            logger.exception("Chat completion failed")
            return AskResponse(
                answer="Unable to generate an answer right now. Please try again later.",
                sources=[ChatSource(id=d["id"], title=d["title"], path=d["path"]) for d in context_docs],
                model=settings.chat_model,
            )

        return AskResponse(
            answer=answer,
            sources=[
                ChatSource(id=d["id"], title=d["title"], path=d["path"])
                for d in context_docs
            ],
            model=settings.chat_model,
        )
