"""Unit tests for DocumentService — the deep module owning document lifecycle.

Tests the service layer directly with an in-memory SQLite database,
bypassing the HTTP stack. Covers ID generation, CRUD, upsert idempotency,
version creation, batch operations, and move logic.
"""

import pytest
from app.services.document_service import DocumentService
from app.schemas.document import DocumentCreate, DocumentUpdate, BatchParams
from app.exceptions import DocumentNotFoundError, ConflictError


def _make_create(
    title: str = "Test Doc",
    path: str = "crate/folder",
    content: str = "# Hello\n\nWorld.",
    **overrides,
) -> DocumentCreate:
    defaults = {
        "repo_url": "https://github.com/org/repo",
        "repo_name": "repo",
        "author_type": "human",
    }
    defaults.update(overrides)
    return DocumentCreate(title=title, path=path, content=content, **defaults)


class TestGenerateDocId:
    """Document ID generation is deterministic and normalizes variants."""

    def test_same_inputs_produce_same_id(self, db):
        svc = DocumentService(db)
        id1 = svc.generate_doc_id("https://github.com/org/repo", "path", "Title")
        id2 = svc.generate_doc_id("https://github.com/org/repo", "path", "Title")
        assert id1 == id2

    def test_trailing_slash_normalized(self, db):
        svc = DocumentService(db)
        id1 = svc.generate_doc_id("https://github.com/org/repo", "p", "T")
        id2 = svc.generate_doc_id("https://github.com/org/repo/", "p", "T")
        assert id1 == id2

    def test_git_suffix_normalized(self, db):
        svc = DocumentService(db)
        id1 = svc.generate_doc_id("https://github.com/org/repo", "p", "T")
        id2 = svc.generate_doc_id("https://github.com/org/repo.git", "p", "T")
        assert id1 == id2

    def test_standalone_doc_prefix(self, db):
        svc = DocumentService(db)
        doc_id = svc.generate_doc_id(None, "notes", "My Note")
        assert doc_id.startswith("doc-standalone-")

    def test_repo_doc_prefix(self, db):
        svc = DocumentService(db)
        doc_id = svc.generate_doc_id("https://github.com/org/repo", "arch", "Overview")
        assert doc_id.startswith("doc-")
        assert "standalone" not in doc_id

    def test_different_paths_produce_different_ids(self, db):
        svc = DocumentService(db)
        id1 = svc.generate_doc_id("https://github.com/org/repo", "arch", "Overview")
        id2 = svc.generate_doc_id("https://github.com/org/repo", "api", "Overview")
        assert id1 != id2

    def test_legacy_doc_type_fallback(self, db):
        svc = DocumentService(db)
        doc_id = svc.generate_doc_id("https://github.com/org/repo", "", "", "architecture")
        assert doc_id.endswith("-architecture")


class TestCreateOrUpdate:
    """Upsert semantics: create new or update existing."""

    def test_create_new_document(self, db):
        svc = DocumentService(db)
        doc, is_new = svc.create_or_update_document(_make_create())
        assert is_new is True
        assert doc.title == "Test Doc"
        assert doc.generation_count == 1

    def test_create_stores_version(self, db):
        svc = DocumentService(db)
        doc, _ = svc.create_or_update_document(_make_create())
        versions = svc.get_document_versions(doc.id)
        assert len(versions) == 1
        assert versions[0].content == "# Hello\n\nWorld."

    def test_upsert_same_document_updates(self, db):
        svc = DocumentService(db)
        doc1, is_new1 = svc.create_or_update_document(_make_create())
        doc2, is_new2 = svc.create_or_update_document(
            _make_create(content="Updated content")
        )
        assert is_new1 is True
        assert is_new2 is False
        assert doc1.id == doc2.id
        assert doc2.content == "Updated content"

    def test_upsert_creates_version(self, db):
        svc = DocumentService(db)
        doc, _ = svc.create_or_update_document(_make_create())
        svc.create_or_update_document(_make_create(content="v2"))
        versions = svc.get_document_versions(doc.id)
        assert len(versions) == 2

    def test_content_preview_generated(self, db):
        svc = DocumentService(db)
        doc, _ = svc.create_or_update_document(_make_create(content="Short content"))
        assert doc.content_preview == "Short content"

    def test_description_stored(self, db):
        svc = DocumentService(db)
        doc, _ = svc.create_or_update_document(
            _make_create(description="A test document about testing.")
        )
        assert doc.description == "A test document about testing."


class TestUpdateDocument:
    """Update with version conflict detection."""

    def _create(self, db, **kwargs):
        svc = DocumentService(db)
        doc, _ = svc.create_or_update_document(_make_create(**kwargs))
        return svc, doc

    def test_update_content(self, db):
        svc, doc = self._create(db)
        updated = svc.update_document(
            doc.id, DocumentUpdate(content="New content", author_type="human")
        )
        assert updated.content == "New content"
        assert updated.generation_count == 2

    def test_update_increments_version(self, db):
        svc, doc = self._create(db)
        original_version = doc.version
        updated = svc.update_document(
            doc.id, DocumentUpdate(content="v2", author_type="human")
        )
        assert updated.version == original_version + 1

    def test_optimistic_lock_conflict(self, db):
        svc, doc = self._create(db)
        stale_version = doc.version  # capture before any updates
        # Update succeeds with correct version
        svc.update_document(
            doc.id,
            DocumentUpdate(content="v2", author_type="human", version=stale_version),
        )
        # Second update with stale version fails (DB is now at version+1)
        with pytest.raises(ConflictError):
            svc.update_document(
                doc.id,
                DocumentUpdate(content="v3", author_type="human", version=stale_version),
            )

    def test_update_nonexistent_raises(self, db):
        svc = DocumentService(db)
        with pytest.raises(DocumentNotFoundError):
            svc.update_document(
                "nonexistent", DocumentUpdate(content="x", author_type="human")
            )


class TestDeleteRestore:
    """Soft delete, restore, and permanent delete lifecycle."""

    def _create(self, db):
        svc = DocumentService(db)
        doc, _ = svc.create_or_update_document(_make_create())
        return svc, doc

    def test_soft_delete_hides_from_list(self, db):
        svc, doc = self._create(db)
        svc.delete_document(doc.id)
        assert svc.get_document(doc.id) is None

    def test_soft_delete_shows_in_trash(self, db):
        svc, doc = self._create(db)
        svc.delete_document(doc.id)
        trash = svc.list_trash()
        assert any(d.id == doc.id for d in trash)

    def test_restore_from_trash(self, db):
        svc, doc = self._create(db)
        svc.delete_document(doc.id)
        restored = svc.restore_document(doc.id)
        assert restored.id == doc.id
        assert svc.get_document(doc.id) is not None

    def test_permanent_delete(self, db):
        svc, doc = self._create(db)
        svc.delete_document(doc.id)
        svc.permanent_delete_document(doc.id)
        trash = svc.list_trash()
        assert all(d.id != doc.id for d in trash)

    def test_delete_is_idempotent(self, db):
        svc, doc = self._create(db)
        assert svc.delete_document(doc.id) is True
        assert svc.delete_document(doc.id) is True  # second call doesn't fail

    def test_permanent_delete_is_idempotent(self, db):
        svc, doc = self._create(db)
        svc.permanent_delete_document(doc.id)
        svc.permanent_delete_document(doc.id)  # no error


class TestMoveDocument:
    """Move document to different folder path."""

    def _create(self, db, **kwargs):
        svc = DocumentService(db)
        doc, _ = svc.create_or_update_document(_make_create(**kwargs))
        return svc, doc

    def test_move_changes_path(self, db):
        svc, doc = self._create(db, path="old/folder")
        moved = svc.move_document(doc.id, "new/folder")
        assert moved.path == "new/folder"

    def test_move_updates_repo_name(self, db):
        svc, doc = self._create(db, path="old-crate/folder")
        moved = svc.move_document(doc.id, "new-crate/folder")
        assert moved.repo_name == "new-crate"

    def test_move_nonexistent_raises(self, db):
        svc = DocumentService(db)
        with pytest.raises(DocumentNotFoundError):
            svc.move_document("nonexistent", "target")


class TestBatchOperations:
    """Batch operations with savepoints and partial failure handling."""

    def _create_docs(self, db, count=3):
        svc = DocumentService(db)
        docs = []
        for i in range(count):
            doc, _ = svc.create_or_update_document(
                _make_create(title=f"Batch Doc {i}", path=f"crate/batch{i}")
            )
            docs.append(doc)
        return svc, docs

    def test_batch_delete(self, db):
        svc, docs = self._create_docs(db)
        ids = [d.id for d in docs]
        result = svc.execute_batch("delete", ids, BatchParams())
        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0

    def test_batch_move(self, db):
        svc, docs = self._create_docs(db)
        ids = [d.id for d in docs]
        result = svc.execute_batch("move", ids, BatchParams(target_path="new/path"))
        assert result.succeeded == 3
        for doc_id in ids:
            doc = svc.get_document(doc_id)
            assert doc.path == "new/path"

    def test_batch_add_keywords(self, db):
        svc, docs = self._create_docs(db)
        ids = [d.id for d in docs]
        result = svc.execute_batch(
            "add_keywords", ids, BatchParams(keywords=["Architecture", "API"])
        )
        assert result.succeeded == 3
        doc = svc.get_document(ids[0])
        assert "Architecture" in doc.keywords

    def test_batch_unknown_operation(self, db):
        svc, docs = self._create_docs(db)
        result = svc.execute_batch("explode", [docs[0].id], BatchParams())
        assert result.failed == 1
        assert result.errors[0].error == "Unknown operation: explode"

    def test_batch_partial_failure(self, db):
        svc, docs = self._create_docs(db)
        ids = [docs[0].id, "nonexistent-id", docs[2].id]
        result = svc.execute_batch("move", ids, BatchParams(target_path="new"))
        assert result.succeeded == 2
        assert result.failed == 1
        assert len(result.errors) == 1

    def test_batch_empty_ids(self, db):
        svc = DocumentService(db)
        result = svc.execute_batch("delete", [], BatchParams())
        assert result.total == 0
        assert result.succeeded == 0
