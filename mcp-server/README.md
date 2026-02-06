# IsoCrates MCP Server

MCP server for querying IsoCrates documentation from AI-powered editors
(Claude Code, Cursor, Codex, or any MCP-compatible client).

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

## Claude Code Setup

Add to your project's `.claude/settings.json` or `~/.claude/settings.json`:

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

Or if installed globally via `uv tool install`:

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

## Available Tools

| Tool | Description | Example |
|------|-------------|---------|
| `search_docs` | Full-text search across all docs | `search_docs("authentication flow")` |
| `get_document` | Get full doc by title or ID | `get_document("Architecture Overview")` |
| `list_documents` | Browse document tree by folder | `list_documents("MyProject/api")` |
| `get_related` | Show wikilink connections | `get_related("Backend Architecture")` |

### search_docs

Search for documents matching a query. Returns titles, paths, and content snippets.

- `query` (required) — search terms
- `path_prefix` (optional) — restrict to a folder
- `limit` (optional, default 10) — max results

### get_document

Retrieve the full content of a document. Accepts either a document title
(resolved via wikilink lookup) or a document ID.

- `title_or_id` (required) — document title or ID

### list_documents

List all documents, optionally filtered by folder path.

- `path_prefix` (optional) — folder to list
- `limit` (optional, default 50) — max results

### get_related

Show incoming and outgoing wikilinks for a document — what it references
and what references it.

- `title_or_id` (required) — document title or ID

## Testing

```bash
# Interactive MCP inspector (requires backend running on localhost:8000)
mcp dev src/isocrates_mcp/server.py

# Verify tools are registered
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | uv run isocrates-mcp
```
