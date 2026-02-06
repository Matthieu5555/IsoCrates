-- dialect: postgresql
-- Migration 012: Add pgvector extension and description embedding column
-- Enables semantic search via cosine similarity on document descriptions.
-- HNSW index provides fast approximate nearest neighbor queries.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE documents ADD COLUMN description_embedding vector(1536);

CREATE INDEX idx_documents_embedding ON documents
USING hnsw (description_embedding vector_cosine_ops)
WHERE description_embedding IS NOT NULL AND deleted_at IS NULL;
