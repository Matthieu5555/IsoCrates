-- Add optimistic locking version column to documents table.
-- Every content update increments this counter. Clients send their
-- known version on update; a mismatch returns HTTP 409 Conflict.

ALTER TABLE documents ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
