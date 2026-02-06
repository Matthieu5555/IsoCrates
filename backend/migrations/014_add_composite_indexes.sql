-- Migration 014: Add composite indexes for common query patterns.
-- Idempotent (IF NOT EXISTS).

-- Most list/search queries filter deleted_at IS NULL then sort by updated_at.
-- A composite index lets the DB satisfy both conditions in one index scan.
CREATE INDEX IF NOT EXISTS ix_documents_active_updated ON documents(deleted_at, updated_at);

-- Title and repo_name lookups used by wikilink resolution (batch IN queries).
CREATE INDEX IF NOT EXISTS ix_documents_title ON documents(title);
CREATE INDEX IF NOT EXISTS ix_documents_repo_name ON documents(repo_name);
