# Database Migrations

This directory contains SQL migrations for the IsoCrates database.

## Migration Files

- `001_make_repo_fields_optional.sql` - Makes repo_url and repo_name nullable to support standalone documents
- `001_rollback_repo_fields.sql` - Rollback script for migration 001 (WARNING: deletes standalone docs)
- `002_add_folder_metadata.sql` - Adds folder_metadata table for empty folders
- `006_add_indexes.sql` - Adds indexes on all key columns (documents, versions, dependencies, personal models). Idempotent (`CREATE INDEX IF NOT EXISTS`).

## Applying Migrations

### Method 1: Using the migration runner (Recommended)

```bash
cd backend/migrations
python apply_migration.py 001_make_repo_fields_optional.sql
```

The script will:
- Create a backup of your database
- Apply the migration
- Automatically restore from backup if the migration fails

### Method 2: Manual application

```bash
cd backend
sqlite3 isocrates.db < migrations/001_make_repo_fields_optional.sql
```

## Rolling Back Migrations

**WARNING**: Rollback scripts may delete data. Always backup first!

```bash
cd backend/migrations
python apply_migration.py 001_rollback_repo_fields.sql
```

## Verifying Migrations

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

## Migration Order

1. `001_make_repo_fields_optional.sql` - Must be applied first
2. `002_add_folder_metadata.sql` - Depends on migration 001
3. `006_add_indexes.sql` - Idempotent, can be applied at any time

## Backup Strategy

The migration runner automatically creates backups with `.backup` extension.

Manual backups:
```bash
cp isocrates.db isocrates.db.backup-$(date +%Y%m%d)
```

## Troubleshooting

If a migration fails:
1. Check the error message
2. Restore from backup: `cp isocrates.db.backup isocrates.db`
3. Review the migration SQL
4. Open an issue with the error details
