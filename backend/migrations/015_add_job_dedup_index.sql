-- Migration 015: Unique partial index for webhook job deduplication.
-- Prevents duplicate queued/running jobs for the same (repo_url, commit_sha) pair.
-- The partial index only covers active jobs, so completed/failed jobs don't block new ones.
-- Works on both SQLite (3.8.0+) and PostgreSQL.

CREATE UNIQUE INDEX IF NOT EXISTS ix_generation_jobs_dedup
ON generation_jobs(repo_url, commit_sha)
WHERE status IN ('queued', 'running') AND commit_sha IS NOT NULL;
