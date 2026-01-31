-- Migration 005: Add soft delete support
-- Adds deleted_at column to documents table for trash/recovery functionality.
-- All existing queries filter on deleted_at IS NULL via the repository layer.

ALTER TABLE documents ADD COLUMN deleted_at TIMESTAMP NULL DEFAULT NULL;

CREATE INDEX idx_documents_deleted_at ON documents(deleted_at);
