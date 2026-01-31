-- Migration 006: Add FTS5 full-text search
-- Creates a virtual table backed by the documents table for fast text search.
-- Triggers keep the FTS index in sync on INSERT/UPDATE/DELETE.
-- Only indexes active (non-deleted) documents.

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    doc_id UNINDEXED,
    title,
    content,
    path,
    keywords
);

-- Populate from existing active documents
INSERT INTO documents_fts(doc_id, title, content, path, keywords)
SELECT
    id,
    title,
    content,
    path,
    COALESCE(
        (SELECT group_concat(value, ' ') FROM json_each(documents.keywords)),
        ''
    )
FROM documents
WHERE deleted_at IS NULL;

-- Keep FTS in sync: INSERT
CREATE TRIGGER IF NOT EXISTS documents_fts_ai AFTER INSERT ON documents
WHEN new.deleted_at IS NULL
BEGIN
    INSERT INTO documents_fts(doc_id, title, content, path, keywords)
    VALUES (
        new.id,
        new.title,
        new.content,
        new.path,
        COALESCE((SELECT group_concat(value, ' ') FROM json_each(new.keywords)), '')
    );
END;

-- Keep FTS in sync: DELETE (hard delete or soft delete)
CREATE TRIGGER IF NOT EXISTS documents_fts_ad AFTER DELETE ON documents
BEGIN
    DELETE FROM documents_fts WHERE doc_id = old.id;
END;

-- Keep FTS in sync: UPDATE
-- Remove old entry and re-insert if still active
CREATE TRIGGER IF NOT EXISTS documents_fts_au AFTER UPDATE ON documents
BEGIN
    DELETE FROM documents_fts WHERE doc_id = old.id;
    INSERT INTO documents_fts(doc_id, title, content, path, keywords)
    SELECT
        new.id,
        new.title,
        new.content,
        new.path,
        COALESCE((SELECT group_concat(value, ' ') FROM json_each(new.keywords)), '')
    WHERE new.deleted_at IS NULL;
END;
