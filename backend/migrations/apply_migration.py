#!/usr/bin/env python3
"""
Simple migration runner for SQLite database.
Usage: python apply_migration.py <migration_file.sql>
"""
import sys
import sqlite3
from pathlib import Path

# Find database file
DB_PATH = Path(__file__).parent.parent / "isocrates.db"

def apply_migration(migration_file: str):
    """Apply a SQL migration file to the database."""
    if not Path(migration_file).exists():
        print(f"Error: Migration file not found: {migration_file}")
        sys.exit(1)

    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        print("Please ensure the backend has been run at least once to create the database.")
        sys.exit(1)

    print(f"Applying migration: {migration_file}")
    print(f"Database: {DB_PATH}")

    # Read migration file
    with open(migration_file, 'r') as f:
        migration_sql = f.read()

    # Create backup
    backup_path = f"{DB_PATH}.backup"
    print(f"Creating backup: {backup_path}")
    import shutil
    shutil.copy2(DB_PATH, backup_path)

    # Apply migration
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Execute migration (SQLite will handle the transaction)
        cursor.executescript(migration_sql)

        conn.commit()
        conn.close()

        print("✓ Migration applied successfully!")
        print(f"Backup saved at: {backup_path}")

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        print(f"Restoring from backup...")
        shutil.copy2(backup_path, DB_PATH)
        print("Database restored to previous state.")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python apply_migration.py <migration_file.sql>")
        sys.exit(1)

    apply_migration(sys.argv[1])
