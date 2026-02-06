#!/bin/bash
# IsoCrates database backup script.
# Supports both SQLite and PostgreSQL databases.
#
# Usage:
#   ./scripts/backup.sh                    # Auto-detect from backend/.env
#   ./scripts/backup.sh /path/to/backup    # Custom backup directory
#   DATABASE_URL=postgresql://... ./scripts/backup.sh

set -euo pipefail

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Load DATABASE_URL from backend/.env if not set
if [ -z "${DATABASE_URL:-}" ]; then
    ENV_FILE="$(dirname "$0")/../backend/.env"
    if [ -f "$ENV_FILE" ]; then
        DATABASE_URL=$(grep -E '^DATABASE_URL=' "$ENV_FILE" | cut -d'=' -f2-)
    fi
fi

if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL not set and not found in backend/.env"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

if [[ "$DATABASE_URL" == sqlite* ]]; then
    # SQLite backup
    # Extract path from sqlite:///./path or sqlite:///path
    DB_PATH=$(echo "$DATABASE_URL" | sed 's|sqlite:///||')
    # Resolve relative paths from backend/
    if [[ "$DB_PATH" == ./* ]]; then
        DB_PATH="$(dirname "$0")/../backend/${DB_PATH#./}"
    fi

    if [ ! -f "$DB_PATH" ]; then
        echo "ERROR: SQLite database not found at $DB_PATH"
        exit 1
    fi

    BACKUP_FILE="$BACKUP_DIR/isocrates_${TIMESTAMP}.db"
    # Use SQLite .backup for a consistent snapshot
    sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"
    echo "SQLite backup created: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

elif [[ "$DATABASE_URL" == postgresql* ]]; then
    # PostgreSQL backup
    BACKUP_FILE="$BACKUP_DIR/isocrates_${TIMESTAMP}.sql.gz"
    pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"
    echo "PostgreSQL backup created: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

else
    echo "ERROR: Unsupported DATABASE_URL scheme: $DATABASE_URL"
    exit 1
fi

# Prune backups older than 30 days
find "$BACKUP_DIR" -name "isocrates_*" -mtime +30 -delete 2>/dev/null && \
    echo "Pruned backups older than 30 days" || true
