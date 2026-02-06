-- dialect: postgresql
-- Migration 013: Rebuild GIN index to include description in full-text search

DROP INDEX IF EXISTS idx_documents_fts;

CREATE INDEX idx_documents_fts ON documents
USING GIN (
    to_tsvector('english',
        COALESCE(title, '') || ' ' ||
        COALESCE(description, '') || ' ' ||
        COALESCE(content, '') || ' ' ||
        COALESCE(path, ''))
);
