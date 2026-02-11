"""HTTP client for the IsoCrates REST API."""

import asyncio
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# Retry configuration for transient failures (connection errors, 5xx).
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds; exponential: 1s, 2s, 4s


class IsoCratesClient:
    """Async client wrapping the IsoCrates backend REST API.

    Configuration via environment variables:
        ISOCRATES_API_URL     — Backend base URL (default: http://localhost:8000)
        ISOCRATES_API_TOKEN   — Optional Bearer token for authenticated access
        ISOCRATES_API_TIMEOUT — Request timeout in seconds (default: 30)
    """

    def __init__(self) -> None:
        self.base_url = os.environ.get("ISOCRATES_API_URL", "http://localhost:8000")
        self.token = os.environ.get("ISOCRATES_API_TOKEN", "")
        self.timeout = float(os.environ.get("ISOCRATES_API_TIMEOUT", "30"))
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute an HTTP request with retry on transient failures.

        Retries on connection errors and 5xx server errors with exponential
        backoff (1s, 2s, 4s). Client errors (4xx) are not retried.
        """
        client = await self._get_client()
        last_exc: Exception | None = None

        for attempt in range(MAX_RETRIES):
            try:
                resp = await client.request(method, path, **kwargs)
                if resp.status_code < 500:
                    resp.raise_for_status()
                    return resp
                # 5xx — retry
                last_exc = httpx.HTTPStatusError(
                    f"Server error {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc

            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Request %s %s failed (attempt %d/%d), retrying in %.1fs: %s",
                    method, path, attempt + 1, MAX_RETRIES, delay, last_exc,
                )
                await asyncio.sleep(delay)

        raise last_exc  # type: ignore[misc]

    async def search(
        self,
        query: str,
        path_prefix: Optional[str] = None,
        limit: int = 10,
        keywords: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Full-text search. Maps to GET /api/docs/search/."""
        params: dict[str, str | int] = {"q": query, "limit": limit}
        if path_prefix:
            params["path_prefix"] = path_prefix
        if keywords:
            params["keywords"] = ",".join(keywords)
        resp = await self._request_with_retry("GET", "/api/docs/search/", params=params)
        return resp.json()

    async def get_document(self, doc_id: str) -> dict[str, Any]:
        """Get full document by ID. Maps to GET /api/docs/{doc_id}."""
        resp = await self._request_with_retry("GET", f"/api/docs/{doc_id}")
        return resp.json()

    async def resolve_wikilink(self, target: str) -> Optional[str]:
        """Resolve a wikilink title to a doc ID. Maps to GET /api/docs/resolve/."""
        try:
            resp = await self._request_with_retry(
                "GET", "/api/docs/resolve/", params={"target": target},
            )
            return resp.json().get("doc_id")
        except httpx.HTTPStatusError:
            return None

    async def list_documents(
        self,
        path_prefix: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List documents. Maps to GET /api/docs."""
        params: dict[str, str | int] = {"limit": limit}
        if path_prefix:
            params["path_prefix"] = path_prefix
        resp = await self._request_with_retry("GET", "/api/docs", params=params)
        return resp.json()

    async def get_dependencies(self, doc_id: str) -> dict[str, Any]:
        """Get wikilink dependencies. Maps to GET /api/docs/{doc_id}/dependencies."""
        resp = await self._request_with_retry("GET", f"/api/docs/{doc_id}/dependencies")
        return resp.json()

    async def batch_titles(self, doc_ids: list[str]) -> dict[str, str]:
        """Resolve doc IDs to titles in one call. Maps to POST /api/docs/batch-titles."""
        if not doc_ids:
            return {}
        resp = await self._request_with_retry(
            "POST", "/api/docs/batch-titles", json={"doc_ids": doc_ids},
        )
        return resp.json()

    async def generate_doc_id(
        self,
        repo_url: Optional[str] = None,
        path: str = "",
        title: str = "",
        doc_type: str = "",
    ) -> str:
        """Generate a stable document ID. Maps to POST /api/docs/generate-id."""
        resp = await self._request_with_retry(
            "POST",
            "/api/docs/generate-id",
            json={"repo_url": repo_url, "path": path, "title": title, "doc_type": doc_type},
        )
        return resp.json()["doc_id"]

    async def find_similar(
        self,
        doc_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find documents similar to a given document. Maps to GET /api/docs/{doc_id}/similar."""
        resp = await self._request_with_retry(
            "GET", f"/api/docs/{doc_id}/similar", params={"limit": limit},
        )
        return resp.json()

    async def find_similar_by_text(
        self,
        text: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find documents similar to arbitrary text. Maps to GET /api/docs/similar/."""
        resp = await self._request_with_retry(
            "GET", "/api/docs/similar/", params={"text": text, "limit": limit},
        )
        return resp.json()

    async def get_latest_version(self, doc_id: str) -> dict[str, Any]:
        """Get latest version metadata. Maps to GET /api/docs/{doc_id}/versions/latest."""
        resp = await self._request_with_retry(
            "GET", f"/api/docs/{doc_id}/versions/latest",
        )
        return resp.json()

    async def create_document(
        self,
        title: str,
        path: str,
        content: str,
        description: Optional[str] = None,
        repo_url: Optional[str] = None,
        repo_name: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        author_type: str = "human",
        author_metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Create or update a document (upsert). Maps to POST /api/docs."""
        payload: dict[str, Any] = {
            "title": title,
            "path": path,
            "content": content,
            "author_type": author_type,
            "author_metadata": author_metadata or {"source": "mcp"},
        }
        if description is not None:
            payload["description"] = description
        if repo_url is not None:
            payload["repo_url"] = repo_url
        if repo_name is not None:
            payload["repo_name"] = repo_name
        if keywords is not None:
            payload["keywords"] = keywords
        resp = await self._request_with_retry("POST", "/api/docs", json=payload)
        return resp.json()

    async def update_document(
        self,
        doc_id: str,
        content: str,
        description: Optional[str] = None,
        author_type: str = "human",
        author_metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Update a document's content. Maps to PUT /api/docs/{doc_id}."""
        payload: dict[str, Any] = {
            "content": content,
            "author_type": author_type,
            "author_metadata": author_metadata or {"source": "mcp"},
        }
        if description is not None:
            payload["description"] = description
        resp = await self._request_with_retry(
            "PUT", f"/api/docs/{doc_id}", json=payload,
        )
        return resp.json()

    async def ask(
        self,
        question: str,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Ask a question via RAG chat. Maps to POST /api/docs/ask/."""
        resp = await self._request_with_retry(
            "POST", "/api/docs/ask/", json={"question": question, "top_k": top_k},
        )
        return resp.json()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
