-- dialect: sqlite
-- Migration 013: Rebuild FTS5 index to include description column
-- Drops and recreates the virtual table + triggers to add description to the search index.

DROP TRIGGER IF EXISTS documents_fts_ai;
DROP TRIGGER IF EXISTS documents_fts_ad;
DROP TRIGGER IF EXISTS documents_fts_au;
DROP TABLE IF EXISTS documents_fts;

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    doc_id UNINDEXED,
    title,
    content,
    path,
    keywords,
    description
);

-- Populate from existing active documents
INSERT INTO documents_fts(doc_id, title, content, path, keywords, description)
SELECT
    id,
    title,
    content,
    path,
    COALESCE(
        (SELECT group_concat(value, ' ') FROM json_each(documents.keywords)),
        ''
    ),
    COALESCE(description, '')
FROM documents
WHERE deleted_at IS NULL;

-- Keep FTS in sync: INSERT
CREATE TRIGGER IF NOT EXISTS documents_fts_ai AFTER INSERT ON documents
WHEN new.deleted_at IS NULL
BEGIN
    INSERT INTO documents_fts(doc_id, title, content, path, keywords, description)
    VALUES (
        new.id,
        new.title,
        new.content,
        new.path,
        COALESCE((SELECT group_concat(value, ' ') FROM json_each(new.keywords)), ''),
        COALESCE(new.description, '')
    );
END;

-- Keep FTS in sync: DELETE
CREATE TRIGGER IF NOT EXISTS documents_fts_ad AFTER DELETE ON documents
BEGIN
    DELETE FROM documents_fts WHERE doc_id = old.id;
END;

-- Keep FTS in sync: UPDATE
CREATE TRIGGER IF NOT EXISTS documents_fts_au AFTER UPDATE ON documents
BEGIN
    DELETE FROM documents_fts WHERE doc_id = old.id;
    INSERT INTO documents_fts(doc_id, title, content, path, keywords, description)
    SELECT
        new.id,
        new.title,
        new.content,
        new.path,
        COALESCE((SELECT group_concat(value, ' ') FROM json_each(new.keywords)), ''),
        COALESCE(new.description, '')
    WHERE new.deleted_at IS NULL;
END;
