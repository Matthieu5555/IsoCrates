"""IsoCrates MCP Server — read and write documentation from AI editors.

Exposes read tools (search, get, list, related, similar) and write tools
(create, update) over stdio transport for use with Claude Code, Cursor,
Codex, or any MCP-compatible client.
"""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from .api_client import IsoCratesClient
from .formatters import (
    format_document,
    format_document_list,
    format_provenance,
    format_related,
    format_search_results,
    format_similar_results,
    format_write_result,
)

mcp = FastMCP("IsoCrates Documentation")
client = IsoCratesClient()


@mcp.tool()
async def search_docs(
    query: str,
    path_prefix: Optional[str] = None,
    limit: int = 10,
    keywords: Optional[list[str]] = None,
) -> str:
    """Full-text search across all documentation.

    Use this to find documents about a topic. Returns titles, paths,
    and content snippets ranked by relevance.

    Args:
        query: Search terms (natural language or keywords)
        path_prefix: Optional folder to search within (e.g. "MyProject/architecture")
        limit: Max results (default 10)
        keywords: Optional tags to filter by (e.g. ["Architecture", "API"])
    """
    try:
        results = await client.search(query, path_prefix, limit, keywords)
        return format_search_results(results)
    except Exception as e:
        return f"Error searching documents: {e}"


@mcp.tool()
async def get_document(title_or_id: str) -> str:
    """Get the full content of a document by its title or ID.

    Tries wikilink resolution first (matches by title), then falls back
    to direct ID lookup. Use search_docs first if you don't know the
    exact title.

    Args:
        title_or_id: Document title (e.g. "Architecture Overview") or document ID
    """
    try:
        # Try wikilink resolution first (title-based lookup)
        doc_id = await client.resolve_wikilink(title_or_id)
        if doc_id:
            doc = await client.get_document(doc_id)
            return format_document(doc)

        # Fall back to direct ID lookup
        try:
            doc = await client.get_document(title_or_id)
            return format_document(doc)
        except Exception:
            return (
                f"Document not found: '{title_or_id}'. "
                "Use search_docs to find the correct title."
            )
    except Exception as e:
        return f"Error retrieving document: {e}"


@mcp.tool()
async def list_documents(
    path_prefix: Optional[str] = None,
    limit: int = 50,
) -> str:
    """List documents in the wiki, optionally filtered by folder path.

    Returns a table of document titles, paths, types, and last-updated dates.

    Args:
        path_prefix: Folder to list (e.g. "MyProject" or "MyProject/architecture")
        limit: Max documents to return (default 50)
    """
    try:
        docs = await client.list_documents(path_prefix, limit)
        return format_document_list(docs)
    except Exception as e:
        return f"Error listing documents: {e}"


@mcp.tool()
async def get_related(title_or_id: str) -> str:
    """Get documents related to a given document via wikilinks.

    Shows both outgoing links (pages this document references) and
    incoming links (pages that reference this document). Useful for
    understanding how topics connect.

    Args:
        title_or_id: Document title or ID
    """
    try:
        # Resolve title to ID
        doc_id = await client.resolve_wikilink(title_or_id)
        doc_title = title_or_id

        if not doc_id:
            # Try as direct ID — fetch the doc to get its title
            try:
                doc = await client.get_document(title_or_id)
                doc_id = title_or_id
                doc_title = doc.get("title", title_or_id)
            except Exception:
                return (
                    f"Document not found: '{title_or_id}'. "
                    "Use search_docs to find the correct title."
                )

        deps = await client.get_dependencies(doc_id)

        # Resolve linked doc IDs to titles for readability
        all_ids: set[str] = set()
        for dep in deps.get("outgoing", []):
            all_ids.add(dep.get("to_doc_id", ""))
        for dep in deps.get("incoming", []):
            all_ids.add(dep.get("from_doc_id", ""))
        all_ids.discard("")

        # Single batch call instead of N+1 individual get_document calls
        title_cache = await client.batch_titles(list(all_ids))

        return format_related(doc_title, deps, title_cache)
    except Exception as e:
        return f"Error getting related documents: {e}"


@mcp.tool()
async def find_similar_docs(
    title_or_id: str,
    limit: int = 5,
) -> str:
    """Find documents semantically similar to a given document.

    Uses vector embeddings to find documents with related content,
    even if they don't share exact keywords. Requires embeddings
    to be configured on the server.

    Args:
        title_or_id: Document title or ID to find similar docs for
        limit: Max results (default 5)
    """
    try:
        # Resolve title to ID
        doc_id = await client.resolve_wikilink(title_or_id)
        if not doc_id:
            # Try as direct ID
            try:
                await client.get_document(title_or_id)
                doc_id = title_or_id
            except Exception:
                return (
                    f"Document not found: '{title_or_id}'. "
                    "Use search_docs to find the correct title."
                )

        results = await client.find_similar(doc_id, limit)
        return format_similar_results(results)
    except Exception as e:
        return f"Error finding similar documents: {e}"


@mcp.tool()
async def get_document_sources(title_or_id: str) -> str:
    """Get the source files and provenance metadata for a document.

    Shows which source code files were used to generate the document,
    the commit SHA, and which models produced it. Useful for tracing
    documentation back to the code it describes.

    Args:
        title_or_id: Document title (e.g. "Architecture Overview") or document ID
    """
    try:
        # Resolve title to ID
        doc_id = await client.resolve_wikilink(title_or_id)
        doc_title = title_or_id

        if not doc_id:
            try:
                doc = await client.get_document(title_or_id)
                doc_id = title_or_id
                doc_title = doc.get("title", title_or_id)
            except Exception:
                return (
                    f"Document not found: '{title_or_id}'. "
                    "Use search_docs to find the correct title."
                )

        version = await client.get_latest_version(doc_id)
        return format_provenance(doc_title, version)
    except Exception as e:
        return f"Error getting document sources: {e}"


@mcp.tool()
async def create_document(
    title: str,
    path: str,
    content: str,
    description: Optional[str] = None,
    repo_url: Optional[str] = None,
    repo_name: Optional[str] = None,
    keywords: Optional[list[str]] = None,
) -> str:
    """Create a new documentation page, or update an existing one with the same title and path.

    Use this after making code changes to capture what changed and why
    while the knowledge is still fresh. The document is stored with
    author_type="human" so the autonomous agent won't overwrite it.

    Args:
        title: Page title (e.g. "Authentication Flow")
        path: Wiki path / folder (e.g. "MyProject/Architecture")
        content: Full markdown content of the page
        description: 2-3 sentence summary for search and embeddings
        repo_url: GitHub URL to associate with this document
        repo_name: Short repo name for display
        keywords: Classification tags (e.g. ["Architecture", "Auth"])
    """
    try:
        doc = await client.create_document(
            title=title,
            path=path,
            content=content,
            description=description,
            repo_url=repo_url,
            repo_name=repo_name,
            keywords=keywords,
        )
        return format_write_result(doc, "Created")
    except Exception as e:
        return f"Error creating document: {e}"


@mcp.tool()
async def update_document(
    title_or_id: str,
    content: str,
    description: Optional[str] = None,
) -> str:
    """Update an existing document's content.

    Use this to revise documentation after code changes. Resolves by
    title first (wikilink-style), then falls back to direct ID lookup.
    Use search_docs or get_document first to find the right page.

    The update is stored with author_type="human" so the autonomous
    agent won't overwrite your changes during regeneration.

    Args:
        title_or_id: Document title (e.g. "Architecture Overview") or document ID
        content: New full markdown content (replaces existing)
        description: Optional updated 2-3 sentence summary
    """
    try:
        # Resolve title to ID
        doc_id = await client.resolve_wikilink(title_or_id)
        if not doc_id:
            # Try as direct ID
            try:
                await client.get_document(title_or_id)
                doc_id = title_or_id
            except Exception:
                return (
                    f"Document not found: '{title_or_id}'. "
                    "Use search_docs to find the correct title."
                )

        doc = await client.update_document(
            doc_id=doc_id,
            content=content,
            description=description,
        )
        return format_write_result(doc, "Updated")
    except Exception as e:
        return f"Error updating document: {e}"


def main() -> None:
    """Entry point — runs the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
