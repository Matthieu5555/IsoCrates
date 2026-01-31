-- Migration 003: Rename collection to crate
-- This migration renames the 'collection' column to 'crate' in both documents and folder_metadata tables
-- to better reflect the terminology used in the application.

-- Rename collection to crate in documents table
ALTER TABLE documents RENAME COLUMN collection TO crate;

-- Rename collection to crate in folder_metadata table
-- SQLite requires recreating the table to change constraints
-- First, create a new table with the updated schema
CREATE TABLE folder_metadata_new (
    id VARCHAR(50) PRIMARY KEY,
    crate VARCHAR(100) NOT NULL,
    path TEXT NOT NULL,
    description TEXT,
    icon VARCHAR(50),
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uix_crate_path UNIQUE (crate, path)
);

-- Copy data from old table to new table
INSERT INTO folder_metadata_new (id, crate, path, description, icon, sort_order, created_at, updated_at)
SELECT id, collection, path, description, icon, sort_order, created_at, updated_at
FROM folder_metadata;

-- Drop old table
DROP TABLE folder_metadata;

-- Rename new table to original name
ALTER TABLE folder_metadata_new RENAME TO folder_metadata;
