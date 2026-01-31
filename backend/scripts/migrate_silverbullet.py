#!/usr/bin/env python3
"""
Migration script to import existing SilverBullet markdown files into the database.
"""

import sys
import re
import hashlib
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal, Base, engine
from app.models import Document, Version, Dependency
from app.repositories import DocumentRepository, VersionRepository, DependencyRepository


def parse_bottomatter(content: str) -> tuple[dict | None, str]:
    """Parse YAML bottom matter from markdown content."""
    pattern = r'\n---\n((?:[^\n]+:[^\n]+\n?)+)---\s*$'
    match = re.search(pattern, content)

    if not match:
        return None, content

    bottomatter_text = match.group(1)
    body = content[:match.start()]

    # Parse YAML (simple key: value parsing)
    metadata = {}
    for line in bottomatter_text.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip().strip('"\'')

    return metadata, body


def parse_frontmatter(content: str) -> tuple[dict | None, str]:
    """Parse YAML frontmatter from markdown content (legacy)."""
    if not content.startswith("---\n"):
        return None, content

    end_match = re.search(r'\n---\n', content[4:])
    if not end_match:
        return None, content

    end_pos = end_match.end() + 4
    frontmatter_text = content[4:end_pos-4]
    body = content[end_pos:]

    # Parse YAML (simple key: value parsing)
    metadata = {}
    for line in frontmatter_text.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            metadata[key.strip()] = value.strip().strip('"\'')

    return metadata, body


def extract_wikilinks(content: str) -> list[str]:
    """Extract wikilinks from content: [[page-name]] or [[page-name|display]]."""
    pattern = r'\[\[([^\]|]+)(?:\|[^\]]*)?\]\]'
    matches = re.findall(pattern, content)
    return matches


def generate_doc_id(repo_url: str, doc_type: str) -> str:
    """Generate stable document ID."""
    repo_hash = hashlib.sha256(repo_url.encode()).hexdigest()[:12]
    return f"doc-{repo_hash}-{doc_type}"


def migrate_documents(notes_dir: Path, db_session):
    """Migrate all documents from notes directory."""
    print(f"\n{'='*70}")
    print("MIGRATING DOCUMENTS FROM SILVERBULLET")
    print(f"{'='*70}\n")

    doc_repo = DocumentRepository(db_session)
    version_repo = VersionRepository(db_session)

    # Track for dependency linking
    doc_id_to_filename = {}
    wikilinks_by_doc = {}

    # Process all markdown files
    md_files = list(notes_dir.glob("*.md"))
    print(f"[Scan] Found {len(md_files)} markdown files")

    migrated_count = 0
    skipped_count = 0

    for md_file in md_files:
        # Skip system files
        if md_file.name.startswith(('.', 'CONFIG', 'SETTINGS', 'PLUGS', 'index')):
            skipped_count += 1
            continue

        try:
            content = md_file.read_text()

            # Try bottom matter first, then frontmatter
            metadata, body = parse_bottomatter(content)
            if not metadata:
                metadata, body = parse_frontmatter(content)

            if not metadata or 'id' not in metadata:
                print(f"[Skip] {md_file.name} - No metadata or ID found")
                skipped_count += 1
                continue

            doc_id = metadata.get('id')
            repo_url = metadata.get('repo_url')
            doc_type = metadata.get('doc_type', 'client')

            if not repo_url:
                print(f"[Skip] {md_file.name} - No repo_url in metadata")
                skipped_count += 1
                continue

            # Extract repo name from URL
            repo_name = repo_url.rstrip('/').split('/')[-1]

            # Create preview
            content_preview = body[:500] if len(body) > 500 else body

            # Check if already exists
            existing = doc_repo.get_by_id(doc_id)
            if existing:
                print(f"[Exists] {doc_id} - Skipping duplicate")
                skipped_count += 1
                continue

            # Create document
            document = Document(
                id=doc_id,
                repo_url=repo_url,
                repo_name=repo_name,
                doc_type=doc_type,
                collection=metadata.get('collection', ''),
                content=body,
                content_preview=content_preview,
                generation_count=1,
                created_at=datetime.fromisoformat(metadata.get('generated_at', datetime.utcnow().isoformat())),
                updated_at=datetime.utcnow()
            )
            db_session.add(document)

            # Create initial version
            version_id = f"{doc_id}-{datetime.utcnow().isoformat().replace(':', '-').replace('.', '-')}"
            content_hash = hashlib.sha256(body.encode()).hexdigest()

            version = Version(
                version_id=version_id,
                doc_id=doc_id,
                content=body,
                content_hash=content_hash,
                author_type=metadata.get('author_type', 'ai'),
                author_metadata={
                    'generator': metadata.get('generator', 'unknown'),
                    'model': metadata.get('model', 'unknown'),
                    'agent': metadata.get('agent', 'unknown')
                },
                created_at=datetime.fromisoformat(metadata.get('generated_at', datetime.utcnow().isoformat()))
            )
            db_session.add(version)

            # Track wikilinks for later dependency creation
            wikilinks = extract_wikilinks(content)
            if wikilinks:
                wikilinks_by_doc[doc_id] = wikilinks

            # Track filename mapping
            doc_id_to_filename[doc_id] = md_file.stem

            print(f"[Migrate] {doc_id} ({doc_type}) - {repo_name}")
            migrated_count += 1

            # Commit periodically
            if migrated_count % 10 == 0:
                db_session.commit()

        except Exception as e:
            print(f"[Error] {md_file.name} - {str(e)}")
            skipped_count += 1
            continue

    # Final commit
    db_session.commit()

    print(f"\n[Summary] Migrated: {migrated_count}, Skipped: {skipped_count}")

    return doc_id_to_filename, wikilinks_by_doc


def migrate_version_history(notes_dir: Path, doc_id_to_filename: dict, db_session):
    """Migrate version history from history/ directory."""
    print(f"\n{'='*70}")
    print("MIGRATING VERSION HISTORY")
    print(f"{'='*70}\n")

    history_dir = notes_dir / "history"
    if not history_dir.exists():
        print("[Skip] No history directory found")
        return

    version_count = 0

    for doc_dir in history_dir.iterdir():
        if not doc_dir.is_dir():
            continue

        doc_id = doc_dir.name

        # Process all version files
        for version_file in sorted(doc_dir.glob("*.md")):
            try:
                content = version_file.read_text()

                # Parse metadata if present
                metadata, body = parse_bottomatter(content)
                if not metadata:
                    metadata, body = parse_frontmatter(content)

                # Extract timestamp from filename
                timestamp_str = version_file.stem  # e.g., "2026-01-29T11-54-23-601022"

                # Convert timestamp format: 2026-01-29T11-54-23-601022 -> 2026-01-29T11:54:23.601022
                # Replace dashes after the T with colons, and the last dash with a dot
                parts = timestamp_str.split('T')
                if len(parts) == 2:
                    date_part = parts[0]
                    time_part = parts[1].replace('-', ':', 2)  # Replace first 2 dashes with colons
                    time_part = time_part.replace('-', '.', 1)  # Replace next dash with dot
                    iso_timestamp = f"{date_part}T{time_part}"
                else:
                    iso_timestamp = timestamp_str

                version_id = f"{doc_id}-{timestamp_str}"
                content_hash = hashlib.sha256(body.encode()).hexdigest()

                version = Version(
                    version_id=version_id,
                    doc_id=doc_id,
                    content=body,
                    content_hash=content_hash,
                    author_type='ai',  # Historical assumption
                    author_metadata=metadata if metadata else {},
                    created_at=datetime.fromisoformat(iso_timestamp)
                )
                db_session.add(version)
                version_count += 1

                if version_count % 20 == 0:
                    db_session.commit()

            except Exception as e:
                print(f"[Error] {version_file.name} - {str(e)}")
                continue

    db_session.commit()
    print(f"[Summary] Migrated {version_count} historical versions")


def create_dependencies(wikilinks_by_doc: dict, doc_id_to_filename: dict, db_session):
    """Create dependency links from wikilinks."""
    print(f"\n{'='*70}")
    print("CREATING DEPENDENCY LINKS")
    print(f"{'='*70}\n")

    dep_repo = DependencyRepository(db_session)
    dependency_count = 0

    # Create reverse lookup (filename -> doc_id)
    filename_to_doc_id = {v: k for k, v in doc_id_to_filename.items()}

    for from_doc_id, wikilinks in wikilinks_by_doc.items():
        for link in wikilinks:
            # Try to resolve wikilink to doc_id
            # Links can be: "page-name", "collection/page-name", etc.
            link_parts = link.split('/')
            link_name = link_parts[-1]

            # Try exact match
            to_doc_id = filename_to_doc_id.get(link_name)

            if to_doc_id:
                try:
                    dependency = Dependency(
                        from_doc_id=from_doc_id,
                        to_doc_id=to_doc_id,
                        link_type='wikilink',
                        link_text=link
                    )
                    db_session.add(dependency)
                    dependency_count += 1
                except Exception as e:
                    print(f"[Error] Failed to create dependency {from_doc_id} -> {to_doc_id}: {e}")

    db_session.commit()
    print(f"[Summary] Created {dependency_count} dependency links")


def main():
    """Run migration."""
    notes_dir = Path("/notes")

    if not notes_dir.exists():
        print(f"[Error] Notes directory not found: {notes_dir}")
        print("[Info] Make sure the script is run in the Docker container with /notes mounted")
        sys.exit(1)

    # Create database tables
    print("[Setup] Creating database tables...")
    Base.metadata.create_all(bind=engine)

    # Create database session
    db = SessionLocal()

    try:
        # Step 1: Migrate documents
        doc_id_to_filename, wikilinks_by_doc = migrate_documents(notes_dir, db)

        # Step 2: Migrate version history
        migrate_version_history(notes_dir, doc_id_to_filename, db)

        # Step 3: Create dependencies
        create_dependencies(wikilinks_by_doc, doc_id_to_filename, db)

        print(f"\n{'='*70}")
        print("MIGRATION COMPLETE!")
        print(f"{'='*70}\n")

    except Exception as e:
        print(f"\n[Fatal Error] Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
