->-- Migration: Add folder metadata table
-- Purpose: Support empty folders without placeholder documents
-- Date: 2026-01-29
-- Depends on: 001_make_repo_fields_optional.sql

BEGIN TRANSACTION;

-- Create folder_metadata table
CREATE TABLE folder_metadata (
    id VARCHAR(50) PRIMARY KEY,
    collection VARCHAR(100) NOT NULL,
    path VARCHAR(500) NOT NULL,
    description TEXT,
    icon VARCHAR(50),
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (collection, path)
);

-- Create indexes for performance
CREATE INDEX idx_folder_metadata_collection ON folder_metadata(collection);
CREATE INDEX idx_folder_metadata_path ON folder_metadata(path);
CREATE INDEX idx_folder_metadata_collection_path ON folder_metadata(collection, path);

COMMIT;

-- Verification query (run after migration):
-- SELECT COUNT(*) as total_folders FROM folder_metadata;
--
-- Example: Create an empty folder
-- INSERT INTO folder_metadata (id, collection, path, description)
-- VALUES ('folder-backend-guides', 'backend', 'guides', 'Backend development guides');
