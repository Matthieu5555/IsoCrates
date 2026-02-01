-- Migration 007: Multi-user permission system
-- Expands users table, adds folder-level grants and audit logging.
--
-- Permission model:
--   - Three roles: admin, editor, viewer
--   - folder_grants controls WHERE a user can operate (path prefix matching)
--   - A user can have different roles in different subtrees
--   - No per-document ownership; version history provides accountability

-- Expand users table for authentication
ALTER TABLE users ADD COLUMN email TEXT UNIQUE;
ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'viewer';
ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1;

-- Path-prefix grants: controls which subtrees a user can access
-- Primary key on (user_id, path_prefix) ensures one grant per user per path.
-- Empty path_prefix ('') means root access (all documents).
CREATE TABLE IF NOT EXISTS folder_grants (
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    path_prefix TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'viewer',
    granted_by TEXT REFERENCES users(user_id),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, path_prefix)
);
CREATE INDEX IF NOT EXISTS idx_folder_grants_user ON folder_grants(user_id);

-- Audit log: records all state-changing operations
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(user_id),
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    details TEXT,
    ip_address TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log(created_at);
