"""Migration: Add path and title columns to documents table."""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def migrate():
    """Add path and title columns if they don't exist."""
    db_path = Path(__file__).parent.parent / "isocrates.db"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns exist
        cursor.execute("PRAGMA table_info(documents)")
        columns = [row[1] for row in cursor.fetchall()]

        # Add path column if missing
        if 'path' not in columns:
            print("Adding 'path' column...")
            cursor.execute("ALTER TABLE documents ADD COLUMN path VARCHAR(500) DEFAULT ''")
            print("✓ Added 'path' column")
        else:
            print("✓ 'path' column already exists")

        # Add title column if missing
        if 'title' not in columns:
            print("Adding 'title' column...")
            cursor.execute("ALTER TABLE documents ADD COLUMN title VARCHAR(255) NOT NULL DEFAULT ''")
            print("✓ Added 'title' column")
        else:
            print("✓ 'title' column already exists")

        conn.commit()
        print("\nMigration completed successfully!")

    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
