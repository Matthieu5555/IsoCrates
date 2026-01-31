-- Rollback Migration 003: Restore collection terminology
-- This rollback script reverts the 'crate' column back to 'collection'

-- Rollback: Rename crate back to collection in documents table
ALTER TABLE documents RENAME COLUMN crate TO collection;

-- Rollback: Restore original constraint name in folder_metadata
ALTER TABLE folder_metadata DROP CONSTRAINT IF EXISTS uix_crate_path;
ALTER TABLE folder_metadata ADD CONSTRAINT uix_collection_path UNIQUE (crate, path);

-- Verify the rollback
SELECT
    'documents' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT collection) as distinct_collections
FROM documents
UNION ALL
SELECT
    'folder_metadata' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT crate) as distinct_crates
FROM folder_metadata;
