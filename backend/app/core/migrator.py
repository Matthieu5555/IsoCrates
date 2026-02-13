"""Database migration runner with automatic tracking.

Handles both fresh installs and existing databases:
- Fresh install: Creates tables via SQLAlchemy, baselines all migrations
- Existing install: Runs pending migrations, tracks in schema_migrations table

Usage:
    from app.core.migrator import run_migrations, MigrationError

    try:
        result = run_migrations(engine)
    except MigrationError as e:
        logger.critical(f"Migration failed: {e}")
        raise SystemExit(1)
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy import Engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Raised when a migration fails to apply."""
    pass


@dataclass
class Migration:
    """A discovered migration file."""
    version: str        # "001", "010"
    name: str           # "make_repo_fields_optional"
    file_path: Path     # Full path to .sql file
    dialect: Optional[str] = None  # None = universal, "postgresql" = PG-only

    def __lt__(self, other: "Migration") -> bool:
        """Sort by version number."""
        return int(self.version) < int(other.version)


@dataclass
class MigrationResult:
    """Result of running migrations."""
    applied: int = 0
    skipped: int = 0
    baselined: int = 0


# Regex to parse migration filenames like "001_make_repo_fields_optional.sql"
_MIGRATION_PATTERN = re.compile(r"^(\d{3})_(.+)\.sql$")

# Regex to parse dialect marker from first line: "-- dialect: postgresql"
_DIALECT_PATTERN = re.compile(r"^--\s*dialect:\s*(sqlite|postgresql)\s*$")


def _get_migrations_dir() -> Path:
    """Get the migrations directory path."""
    return Path(__file__).parent.parent.parent / "migrations"


def _discover_migration_files() -> list[Migration]:
    """Scan migrations directory for .sql files.

    Skips rollback files (containing "rollback" in name).
    Returns sorted list of Migration objects.
    """
    migrations_dir = _get_migrations_dir()

    if not migrations_dir.exists():
        logger.warning(f"Migrations directory not found: {migrations_dir}")
        return []

    migrations = []
    for file_path in sorted(migrations_dir.glob("*.sql")):
        # Skip rollback files
        if "rollback" in file_path.name.lower():
            continue

        match = _MIGRATION_PATTERN.match(file_path.name)
        if match:
            version = match.group(1)
            name = match.group(2)

            # Check first line for dialect marker (e.g., "-- dialect: postgresql")
            dialect = None
            first_line = file_path.read_text().split("\n", 1)[0]
            dialect_match = _DIALECT_PATTERN.match(first_line)
            if dialect_match:
                dialect = dialect_match.group(1)

            migrations.append(Migration(version=version, name=name, file_path=file_path, dialect=dialect))
        else:
            logger.debug(f"Skipping non-migration file: {file_path.name}")

    return sorted(migrations)


def _is_fresh_install(engine: Engine) -> bool:
    """Check if this is a fresh install (no documents table)."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    return "documents" not in tables


def _get_schema_state(engine: Engine) -> dict:
    """Get current schema state for migration detection."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    doc_columns = set()
    if "documents" in tables:
        doc_columns = {col["name"] for col in inspector.get_columns("documents")}

    # Check for PostgreSQL FTS GIN index (created by 010_add_fts_postgres.sql)
    has_fts_index = False
    if engine.dialect.name == "postgresql" and "documents" in tables:
        indexes = inspector.get_indexes("documents")
        has_fts_index = any(idx["name"] == "idx_documents_fts" for idx in indexes)

    return {
        "tables": tables,
        "doc_columns": doc_columns,
        "has_fts_index": has_fts_index,
    }


# Migration checksums: what schema changes each migration makes
# Used to detect which migrations are already applied
_MIGRATION_CHECKS = {
    # 001-007: Schema changes that are now baked into models
    # If 'documents' table exists without 'collection' column, these are done
    "001": lambda s: "documents" in s["tables"] and "collection" not in s["doc_columns"],
    "002": lambda s: "folder_metadata" in s["tables"],
    "003": lambda s: "documents" in s["tables"],  # rename is done if table exists
    "004": lambda s: "personal_folders" in s["tables"],
    "005": lambda s: "deleted_at" in s["doc_columns"],
    "006": lambda s: True,  # Index-only, always consider done if tables exist
    "007": lambda s: "folder_grants" in s["tables"],
    # Later migrations add specific features
    "008": lambda s: "version" in s["doc_columns"],
    # PostgreSQL: check for GIN FTS index created by migration 010.
    "010": lambda s: s.get("has_fts_index", False),
}


def _detect_applied_migrations(engine: Engine, migrations: list[Migration]) -> set[str]:
    """Detect which migrations are already applied based on schema state.

    Returns set of version strings that should be baselined.
    """
    state = _get_schema_state(engine)

    # If no documents table, nothing is applied
    if "documents" not in state["tables"]:
        return set()

    applied = set()
    for migration in migrations:
        check = _MIGRATION_CHECKS.get(migration.version)
        if check and check(state):
            applied.add(migration.version)

    return applied


def _schema_migrations_exists(engine: Engine) -> bool:
    """Check if schema_migrations table exists."""
    inspector = inspect(engine)
    return "schema_migrations" in inspector.get_table_names()


def _ensure_migrations_table(engine: Engine) -> None:
    """Create schema_migrations table if it doesn't exist."""
    if _schema_migrations_exists(engine):
        return

    logger.info("Creating schema_migrations table")

    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE schema_migrations (
                version VARCHAR(10) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.commit()


def _get_applied_versions(engine: Engine) -> set[str]:
    """Query schema_migrations for already-applied versions."""
    if not _schema_migrations_exists(engine):
        return set()

    with engine.connect() as conn:
        result = conn.execute(text("SELECT version FROM schema_migrations"))
        return {row[0] for row in result}


def _record_migration(engine: Engine, migration: Migration) -> None:
    """Record a migration as applied in schema_migrations."""
    with engine.connect() as conn:
        conn.execute(
            text("INSERT INTO schema_migrations (version, name) VALUES (:version, :name)"),
            {"version": migration.version, "name": migration.name}
        )
        conn.commit()


def _apply_migration(engine: Engine, migration: Migration) -> None:
    """Execute a migration's SQL and record it as applied.

    Raises MigrationError on failure.
    """
    sql_content = migration.file_path.read_text()

    with engine.connect() as conn:
        try:
            conn.execute(text(sql_content))
            conn.commit()
        except SQLAlchemyError as e:
            raise MigrationError(f"Failed to apply {migration.version}_{migration.name}: {e}") from e

    # Record as applied
    _record_migration(engine, migration)


def _baseline_migrations(engine: Engine, migrations: list[Migration]) -> None:
    """Mark all migrations as applied without running them (fresh install)."""
    for migration in migrations:
        _record_migration(engine, migration)
        logger.debug(f"Baselined migration {migration.version}: {migration.name}")


def run_migrations(engine: Engine, base: type) -> MigrationResult:
    """Run all pending migrations. Idempotent.

    Args:
        engine: SQLAlchemy engine
        base: SQLAlchemy declarative base (for create_all on fresh install)

    Returns:
        MigrationResult with counts of applied/skipped/baselined migrations

    Raises:
        MigrationError: If a migration fails to apply
    """
    logger.info("Starting migration check")

    all_migrations = _discover_migration_files()

    # Keep universal migrations (dialect=None) and postgresql-specific ones.
    # Skip migrations targeted at other dialects.
    migrations = [
        m for m in all_migrations
        if m.dialect is None or m.dialect == "postgresql"
    ]
    skipped = len(all_migrations) - len(migrations)
    if skipped:
        logger.info(f"Skipped {skipped} non-postgresql migration(s)")
    logger.debug(f"Discovered {len(migrations)} applicable migration files")

    # Phase 1: Detect install state
    if _is_fresh_install(engine):
        logger.info("Fresh install detected - creating tables from models")

        # Create all tables from SQLAlchemy models
        base.metadata.create_all(bind=engine)

        # Create migrations table and baseline all
        _ensure_migrations_table(engine)
        _baseline_migrations(engine, migrations)

        logger.info(f"Baselined {len(migrations)} migrations")
        return MigrationResult(baselined=len(migrations))

    # Phase 2: Existing install - check what needs to be done
    logger.info("Existing install detected")
    _ensure_migrations_table(engine)

    # Get versions already tracked in schema_migrations
    tracked_versions = _get_applied_versions(engine)

    # Detect migrations that are applied but not tracked (schema inspection)
    detected_applied = _detect_applied_migrations(engine, migrations)

    # Baseline any detected-as-applied but not tracked
    newly_baselined = detected_applied - tracked_versions
    if newly_baselined:
        logger.info(f"Detected {len(newly_baselined)} already-applied migration(s) - baselining")
        for m in migrations:
            if m.version in newly_baselined:
                _record_migration(engine, m)
                logger.debug(f"Baselined migration {m.version}: {m.name}")

    # Now get the full set of applied versions
    applied_versions = tracked_versions | detected_applied
    pending = [m for m in migrations if m.version not in applied_versions]

    if not pending:
        if newly_baselined:
            logger.info(f"Baselined {len(newly_baselined)} migrations, no pending migrations")
            return MigrationResult(baselined=len(newly_baselined))
        logger.info("No pending migrations")
        return MigrationResult(skipped=len(migrations))

    logger.info(f"Found {len(pending)} pending migration(s)")

    # Apply pending migrations
    applied_count = 0
    for migration in pending:
        logger.info(f"Applying migration {migration.version}: {migration.name}")
        _apply_migration(engine, migration)
        applied_count += 1
        logger.info(f"Applied migration {migration.version}")

    logger.info(f"Applied {applied_count} migration(s) successfully")
    return MigrationResult(applied=applied_count)
