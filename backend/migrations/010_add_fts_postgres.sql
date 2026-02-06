-- dialect: postgresql
-- Migration 010: Add full-text search indexes (PostgreSQL only)
-- Uses GIN index on tsvector for fast text search.
-- The search_fts_postgresql() method in document_repository.py builds
-- tsvector/tsquery at query time, so this index accelerates those queries.

-- Combined tsvector index on title + content + path for document search.
-- GIN indexes support fast containment queries on tsvector columns.
CREATE INDEX IF NOT EXISTS idx_documents_fts
ON documents
USING GIN (
    to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(content, '') || ' ' || COALESCE(path, ''))
);
