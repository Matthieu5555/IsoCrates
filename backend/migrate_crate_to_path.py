"""Migration: merge crate column into path for both documents and folder_metadata tables."""

import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "isocrates.db")


def migrate(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Check if crate column still exists
    cur.execute("PRAGMA table_info(documents)")
    doc_cols = [row[1] for row in cur.fetchall()]
    if "crate" not in doc_cols:
        print("Migration already applied (no crate column). Skipping.")
        conn.close()
        return

    print(f"Migrating {db_path}...")

    # --- documents table ---
    # Merge crate into path: path = crate/path (or just crate if path is empty)
    cur.execute("""
        UPDATE documents
        SET path = CASE
            WHEN crate != '' AND path != '' THEN crate || '/' || path
            WHEN crate != '' AND path = '' THEN crate
            ELSE path
        END
    """)
    print(f"  Updated {cur.rowcount} document paths")

    # Recreate documents table without crate column
    cur.execute("""
        CREATE TABLE documents_new (
            id VARCHAR(50) PRIMARY KEY,
            repo_url TEXT,
            repo_name VARCHAR(255),
            path VARCHAR(500) DEFAULT '',
            title VARCHAR(255) NOT NULL,
            doc_type VARCHAR(100) DEFAULT '',
            content TEXT NOT NULL,
            content_preview TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            generation_count INTEGER DEFAULT 1
        )
    """)
    cur.execute("""
        INSERT INTO documents_new (id, repo_url, repo_name, path, title, doc_type,
                                   content, content_preview, created_at, updated_at, generation_count)
        SELECT id, repo_url, repo_name, path, title, doc_type,
               content, content_preview, created_at, updated_at, generation_count
        FROM documents
    """)
    cur.execute("DROP TABLE documents")
    cur.execute("ALTER TABLE documents_new RENAME TO documents")
    cur.execute("CREATE INDEX idx_documents_path ON documents(path)")
    cur.execute("CREATE INDEX idx_documents_repo_name ON documents(repo_name)")
    cur.execute("CREATE INDEX idx_documents_updated_at ON documents(updated_at DESC)")
    print("  Recreated documents table without crate column")

    # --- folder_metadata table ---
    # Merge crate into path
    cur.execute("""
        UPDATE folder_metadata
        SET path = CASE
            WHEN crate != '' AND path != '' THEN crate || '/' || path
            WHEN crate != '' AND path = '' THEN crate
            ELSE path
        END
    """)
    print(f"  Updated {cur.rowcount} folder_metadata paths")

    # Recreate folder_metadata table without crate column
    cur.execute("""
        CREATE TABLE folder_metadata_new (
            id VARCHAR(50) PRIMARY KEY,
            path TEXT NOT NULL UNIQUE,
            description TEXT,
            icon VARCHAR(50),
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        INSERT INTO folder_metadata_new (id, path, description, icon, sort_order, created_at, updated_at)
        SELECT id, path, description, icon, sort_order, created_at, updated_at
        FROM folder_metadata
    """)
    cur.execute("DROP TABLE folder_metadata")
    cur.execute("ALTER TABLE folder_metadata_new RENAME TO folder_metadata")
    print("  Recreated folder_metadata table without crate column")

    conn.commit()
    conn.close()
    print("Migration complete.")


if __name__ == "__main__":
    migrate()
