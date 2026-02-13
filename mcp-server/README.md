# IsoCrates MCP Server

This is an MCP server for querying IsoCrates documentation from AI-powered editors such as Claude Code, Cursor, Codex, or any MCP-compatible client. Think of it as a librarian that sits inside your editor, fetching the right documentation page whenever an AI tool asks for it.

## Installation

```bash
cd mcp-server
uv pip install -e .
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ISOCRATES_API_URL` | `http://localhost:8000` | IsoCrates backend URL |
| `ISOCRATES_API_TOKEN` | *(empty)* | Bearer token (required when `AUTH_ENABLED=true`) |

## Claude Code setup

Add the following to your project's `.claude/settings.json` or `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "isocrates": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/IsoCrates/mcp-server", "isocrates-mcp"],
      "env": {
        "ISOCRATES_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

If you installed the package globally via `uv tool install`, the config is simpler:

```json
{
  "mcpServers": {
    "isocrates": {
      "command": "isocrates-mcp",
      "env": {
        "ISOCRATES_API_URL": "http://localhost:8000"
      }
    }
  }
}
```

## Available tools

| Tool | Description | Example |
|------|-------------|---------|
| `search_docs` | Full-text search across all docs | `search_docs("authentication flow")` |
| `get_document` | Get full doc by title or ID | `get_document("Architecture Overview")` |
| `list_documents` | Browse document tree by folder | `list_documents("MyProject/api")` |
| `get_related` | Show wikilink connections | `get_related("Backend Architecture")` |

### search_docs

Searches for documents matching a query and returns titles, paths, and content snippets. The `query` parameter is required. You can optionally pass `path_prefix` to restrict results to a folder, and `limit` (default 10) to cap the number of results.

### get_document

Retrieves the full content of a document. Pass `title_or_id`, which can be either a document title (resolved via wikilink lookup) or a document ID.

### list_documents

Lists all documents, optionally filtered by folder path. Pass `path_prefix` to narrow results to a folder, and `limit` (default 50) to cap the count.

### get_related

Shows incoming and outgoing wikilinks for a document, revealing what it references and what references it. Pass `title_or_id` to identify the document by title or ID.

## Testing

```bash
# Interactive MCP inspector (requires backend running on localhost:8000)
mcp dev src/isocrates_mcp/server.py

# Verify tools are registered
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | uv run isocrates-mcp
```
