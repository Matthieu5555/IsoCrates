# Database Migrations

This directory contains SQL migrations for the IsoCrates database. Think of each migration as a recipe that changes the shape of your database tables, and the migration runner as a careful chef that makes a backup before trying anything new.

## Migration files

| File | Purpose |
|------|---------|
| `001_make_repo_fields_optional.sql` | Makes `repo_url` and `repo_name` nullable to support standalone documents |
| `001_rollback_repo_fields.sql` | Rollback script for migration 001 (deletes standalone docs, so use with caution) |
| `002_add_folder_metadata.sql` | Adds the `folder_metadata` table for empty folders |
| `006_add_indexes.sql` | Adds indexes on all key columns (documents, versions, dependencies, personal models). Idempotent via `CREATE INDEX IF NOT EXISTS`. |

## Applying migrations

### Method 1: Using the migration runner (recommended)

```bash
cd backend/migrations
python apply_migration.py 001_make_repo_fields_optional.sql
```

The script creates a backup of your database, applies the migration, and automatically restores from the backup if anything fails.

### Method 2: Manual application

```bash
cd backend
sqlite3 isocrates.db < migrations/001_make_repo_fields_optional.sql
```

## Rolling back migrations

Rollback scripts may delete data, so always back up first.

```bash
cd backend/migrations
python apply_migration.py 001_rollback_repo_fields.sql
```

## Verifying migrations

After applying migration 001, verify it worked:

```bash
cd backend
sqlite3 isocrates.db

sqlite> .schema documents
-- Should show repo_url and repo_name as nullable (no NOT NULL constraint)

sqlite> SELECT COUNT(*) as total_docs,
        COUNT(repo_url) as docs_with_repo,
        COUNT(*) - COUNT(repo_url) as standalone_docs
FROM documents;
```

## Migration order

Migrations must be applied in sequence. Migration 001 goes first, migration 002 depends on 001, and migration 006 is idempotent so it can be applied at any time.

## Backup strategy

The migration runner automatically creates backups with a `.backup` extension. For manual backups:

```bash
cp isocrates.db isocrates.db.backup-$(date +%Y%m%d)
```

## Troubleshooting

If a migration fails, check the error message, then restore from your backup with `cp isocrates.db.backup isocrates.db`. Review the migration SQL to understand what went wrong, and if you are still stuck, open an issue with the error details.
