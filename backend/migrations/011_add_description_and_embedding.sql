-- Migration 011: Add description and embedding tracking columns
-- description: AI-generated 2-3 sentence summary for semantic search and MCP discovery
-- embedding_model: tracks which LLM embedding model was used (for re-indexing detection)

ALTER TABLE documents ADD COLUMN description TEXT;
ALTER TABLE documents ADD COLUMN embedding_model TEXT;
