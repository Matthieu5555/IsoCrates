-- Migration 006: Add indexes to frequently queried columns.
-- All statements are idempotent (IF NOT EXISTS) so re-running is safe.

-- documents: tree queries, sorting, repo grouping
CREATE INDEX IF NOT EXISTS ix_documents_path ON documents(path);
CREATE INDEX IF NOT EXISTS ix_documents_updated_at ON documents(updated_at);
CREATE INDEX IF NOT EXISTS ix_documents_repo_url ON documents(repo_url);

-- versions: lookup by document, chronological ordering
CREATE INDEX IF NOT EXISTS ix_versions_doc_id ON versions(doc_id);
CREATE INDEX IF NOT EXISTS ix_versions_created_at ON versions(created_at);

-- dependencies: graph traversal, duplicate prevention
CREATE INDEX IF NOT EXISTS ix_dependencies_from_doc_id ON dependencies(from_doc_id);
CREATE INDEX IF NOT EXISTS ix_dependencies_to_doc_id ON dependencies(to_doc_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_dependencies_pair ON dependencies(from_doc_id, to_doc_id);

-- personal_folders: per-user queries, tree traversal
CREATE INDEX IF NOT EXISTS ix_personal_folders_user_id ON personal_folders(user_id);
CREATE INDEX IF NOT EXISTS ix_personal_folders_parent_id ON personal_folders(parent_id);

-- personal_document_refs: per-user-folder lookup, document reverse lookup
CREATE INDEX IF NOT EXISTS ix_personal_refs_user_folder ON personal_document_refs(user_id, folder_id);
CREATE INDEX IF NOT EXISTS ix_personal_refs_document_id ON personal_document_refs(document_id);
