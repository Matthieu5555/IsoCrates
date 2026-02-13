# Database Migrations

SQL migrations for the IsoCrates PostgreSQL database. The migration runner (`app.core.migrator`) applies them automatically on startup.

## How it works

- On **fresh install**: tables are created from SQLAlchemy models, all migrations are baselined (recorded as applied without running).
- On **existing install**: pending migrations are run in version order.
- Migrations are tracked in the `schema_migrations` table.

## File naming

```
{version}_{name}.sql          - universal migration
{version}_{name}.sql           - with "-- dialect: postgresql" on line 1 for PG-only
```

Version is a 3-digit zero-padded number (e.g., `001`, `014`). Files are applied in version order.

## Applying migrations

Migrations run automatically when the backend starts. No manual steps needed.

To check migration status:

```sql
SELECT * FROM schema_migrations ORDER BY version;
```

## Backup strategy

Use `pg_dump` before major migrations:

```bash
pg_dump -U isocrates isocrates > backup_$(date +%Y%m%d).sql
```

## Adding a new migration

1. Create `{next_version}_{descriptive_name}.sql` in this directory
2. Add `-- dialect: postgresql` on line 1 if PG-specific syntax is used
3. Restart the backend - the migration will be applied automatically
