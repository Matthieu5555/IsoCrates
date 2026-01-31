-- Rollback Migration 001: Restore NOT NULL constraints on repository fields
-- WARNING: This will DELETE any standalone documents without repo_url/repo_name
-- Date: 2026-01-29

BEGIN TRANSACTION;

-- First, delete any standalone documents (those without repo_url or repo_name)
DELETE FROM documents WHERE repo_url IS NULL OR repo_name IS NULL;

-- Create new table with NOT NULL constraints
CREATE TABLE documents_new (
    id VARCHAR(50) PRIMARY KEY,
    repo_url TEXT NOT NULL,
    repo_name VARCHAR(255) NOT NULL,
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

-- Copy remaining data
INSERT INTO documents_new
SELECT id, repo_url, repo_name, collection, path, title, doc_type, content,
       content_preview, created_at, updated_at, generation_count
FROM documents
WHERE repo_url IS NOT NULL AND repo_name IS NOT NULL;

-- Drop old table
DROP TABLE documents;

-- Rename new table
ALTER TABLE documents_new RENAME TO documents;

-- Recreate indexes
CREATE INDEX idx_documents_collection ON documents(collection);
CREATE INDEX idx_documents_repo_name ON documents(repo_name);
CREATE INDEX idx_documents_path ON documents(path);
CREATE INDEX idx_documents_updated_at ON documents(updated_at DESC);

COMMIT;
