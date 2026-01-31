#!/usr/bin/env python3
"""
Migration script: Add hierarchical folder support

What this does:
1. Adds 'path' column (String 500) - folder hierarchy like "User Guide/Advanced"
2. Adds 'title' column (String 255) - document name like "Getting Started"
3. Migrates existing documents:
   - Sets path="" (root level)
   - Sets title="{repo_name} - {doc_type}" (e.g., "FastAPI - Client")
4. Verifies all documents have titles

⚠️  This script is idempotent - safe to run multiple times.
    It checks if columns exist before adding them.

After running:
- Restart backend: docker-compose restart backend-api
- Existing docs appear at root level of their repository
- New docs can use hierarchical paths
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.database import engine, SessionLocal
from app.models import Document


def migrate():
    """Run migration to add hierarchical support."""
    print("="*70)
    print("MIGRATION: Adding Hierarchical Folder Support")
    print("="*70)
    
    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("PRAGMA table_info(documents)"))
        columns = {row[1] for row in result}
        
        has_path = 'path' in columns
        has_title = 'title' in columns
        
        if has_path and has_title:
            print("\n✓ Columns already exist. Nothing to migrate.")
            return
        
        print("\n[1/3] Adding new columns...")
        
        # Add path column if needed
        if not has_path:
            conn.execute(text("ALTER TABLE documents ADD COLUMN path VARCHAR(500) DEFAULT ''"))
            print("  ✓ Added 'path' column")
        
        # Add title column if needed  
        if not has_title:
            conn.execute(text("ALTER TABLE documents ADD COLUMN title VARCHAR(255)"))
            print("  ✓ Added 'title' column")
        
        # Expand doc_type column size
        # SQLite doesn't support ALTER COLUMN, so we note it for new tables
        print("  ⓘ Note: doc_type size will be 100 chars for new rows")
        
        conn.commit()
    
    print("\n[2/3] Migrating existing documents...")
    
    db = SessionLocal()
    try:
        documents = db.query(Document).all()
        
        for doc in documents:
            # Set title from repo_name + doc_type if not set
            if not doc.title:
                if doc.doc_type in ['client', 'softdev']:
                    doc.title = f"{doc.repo_name} - {doc.doc_type.title()}"
                else:
                    doc.title = doc.repo_name
            
            # Ensure path is set (empty string for root level)
            if not hasattr(doc, 'path') or doc.path is None:
                doc.path = ""
        
        db.commit()
        print(f"  ✓ Migrated {len(documents)} documents")
        
    finally:
        db.close()
    
    print("\n[3/3] Verifying migration...")
    
    db = SessionLocal()
    try:
        docs_with_title = db.query(Document).filter(Document.title != None).count()
        total_docs = db.query(Document).count()
        
        print(f"  ✓ {docs_with_title}/{total_docs} documents have titles")
        
        if docs_with_title == total_docs:
            print("\n" + "="*70)
            print("✓ MIGRATION COMPLETE")
            print("="*70)
            print("\nNext steps:")
            print("1. Restart the backend service")
            print("2. Existing documents will appear in the tree")
            print("3. New documents can use hierarchical paths")
        else:
            print("\n⚠ Warning: Some documents still missing titles")
            
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
