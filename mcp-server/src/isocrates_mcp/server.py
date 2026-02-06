"""IsoCrates MCP Server — query documentation from AI editors.

Exposes four tools over stdio transport for use with Claude Code,
Cursor, Codex, or any MCP-compatible client.
"""

from typing import Optional

from mcp.server.fastmcp import FastMCP

from .api_client import IsoCratesClient
from .formatters import (
    format_document,
    format_document_list,
    format_related,
    format_search_results,
    format_similar_results,
)

mcp = FastMCP("IsoCrates Documentation")
client = IsoCratesClient()


@mcp.tool()
async def search_docs(
    query: str,
    path_prefix: Optional[str] = None,
    limit: int = 10,
) -> str:
    """Full-text search across all documentation.

    Use this to find documents about a topic. Returns titles, paths,
    and content snippets ranked by relevance.

    Args:
        query: Search terms (natural language or keywords)
        path_prefix: Optional folder to search within (e.g. "MyProject/architecture")
        limit: Max results (default 10)
    """
    try:
        results = await client.search(query, path_prefix, limit)
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


def main() -> None:
    """Entry point — runs the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
