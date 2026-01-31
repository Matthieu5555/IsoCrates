-- Migration 004: Add personal tree tables (users, personal_folders, personal_document_refs)
-- This enables per-user organization of document references

-- Users table (default user for now, future auth-ready)
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY DEFAULT 'default',
    display_name TEXT NOT NULL DEFAULT 'Default User',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default user
INSERT OR IGNORE INTO users (user_id, display_name) VALUES ('default', 'Default User');

-- Personal folders (user's own folder hierarchy)
CREATE TABLE IF NOT EXISTS personal_folders (
    folder_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    name TEXT NOT NULL,
    parent_id TEXT REFERENCES personal_folders(folder_id) ON DELETE CASCADE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, parent_id, name)
);

-- Personal document references (links to org documents, not copies)
CREATE TABLE IF NOT EXISTS personal_document_refs (
    ref_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id),
    folder_id TEXT NOT NULL REFERENCES personal_folders(folder_id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, folder_id, document_id)
);
