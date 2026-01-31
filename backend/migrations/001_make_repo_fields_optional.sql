-- Migration: Make repository fields optional
-- Purpose: Allow documents to exist without being tied to a GitHub repository
-- Date: 2026-01-29

-- SQLite doesn't support ALTER COLUMN directly, so we need to:
-- 1. Create new table with nullable fields
-- 2. Copy data
-- 3. Drop old table
-- 4. Rename new table

BEGIN TRANSACTION;

-- Create new table with nullable repo fields
CREATE TABLE documents_new (
    id VARCHAR(50) PRIMARY KEY,
    repo_url TEXT,
    repo_name VARCHAR(255),
    collection VARCHAR(100) DEFAULT '',
    path VARCHAR(500) DEFAULT '',
    title VARCHAR(255) NOT NULL,
    doc_type VARCHAR(100) DEFAULT '',
    content TEXT NOT NULL,
    content_preview TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    generation_count INTEGER DEFAULT 1
);

-- Copy all existing data
INSERT INTO documents_new
SELECT id, repo_url, repo_name, collection, path, title, doc_type, content,
       content_preview, created_at, updated_at, generation_count
FROM documents;

-- Drop old table
DROP TABLE documents;

-- Rename new table to documents
ALTER TABLE documents_new RENAME TO documents;

-- Recreate indexes for performance
CREATE INDEX idx_documents_collection ON documents(collection);
CREATE INDEX idx_documents_repo_name ON documents(repo_name);
CREATE INDEX idx_documents_path ON documents(path);
CREATE INDEX idx_documents_updated_at ON documents(updated_at DESC);

COMMIT;

-- Verification query (run after migration):
-- SELECT COUNT(*) as total_docs,
--        COUNT(repo_url) as docs_with_repo,
--        COUNT(*) - COUNT(repo_url) as standalone_docs
-- FROM documents;
