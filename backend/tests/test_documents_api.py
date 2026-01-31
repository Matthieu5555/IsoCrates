"""Tests for the /api/docs endpoints — the deep interface of the document system.

Covers the full CRUD lifecycle, upsert idempotency, search, and path filtering.
"""

from tests.conftest import make_document


class TestDocumentCRUD:
    """Create → Read → Update → Delete lifecycle."""

    def test_create_document(self, client):
        payload = make_document()
        resp = client.post("/api/docs", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Document"
        assert data["path"] == "test-crate/docs"
        assert "id" in data

    def test_get_document(self, client):
        payload = make_document()
        create_resp = client.post("/api/docs", json=payload)
        doc_id = create_resp.json()["id"]

        resp = client.get(f"/api/docs/{doc_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == doc_id

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get("/api/docs/doc-does-not-exist")
        assert resp.status_code == 404

    def test_update_document(self, client):
        payload = make_document()
        doc_id = client.post("/api/docs", json=payload).json()["id"]

        resp = client.put(f"/api/docs/{doc_id}", json={"content": "Updated content", "author_type": "human"})
        assert resp.status_code == 200
        assert "Updated content" in resp.json()["content"]

    def test_delete_document(self, client):
        payload = make_document()
        doc_id = client.post("/api/docs", json=payload).json()["id"]

        resp = client.delete(f"/api/docs/{doc_id}")
        assert resp.status_code == 204

    def test_list_documents(self, client):
        client.post("/api/docs", json=make_document(title="Doc A"))
        client.post("/api/docs", json=make_document(title="Doc B", path="other-crate"))

        resp = client.get("/api/docs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2


class TestUpsertIdempotency:
    """POSTing the same document twice should update, not duplicate."""

    def test_upsert_same_document(self, client):
        payload = make_document(title="Upsert Test", path="crate/folder")
        resp1 = client.post("/api/docs", json=payload)
        doc_id_1 = resp1.json()["id"]

        payload["content"] = "Updated via upsert"
        resp2 = client.post("/api/docs", json=payload)
        doc_id_2 = resp2.json()["id"]

        assert doc_id_1 == doc_id_2
        assert resp2.json()["content"] == "Updated via upsert"


class TestSearch:

    def test_search_returns_results(self, client):
        client.post("/api/docs", json=make_document(content="unique_search_term_xyz"))
        resp = client.get("/api/docs/search/", params={"q": "unique_search_term_xyz"})
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_search_no_results(self, client):
        resp = client.get("/api/docs/search/", params={"q": "nonexistent_gibberish_abc123"})
        assert resp.status_code == 200
        assert resp.json() == []


class TestSoftDelete:
    """Soft delete, trash, restore, and permanent delete lifecycle."""

    def _create(self, client, **kwargs):
        resp = client.post("/api/docs", json=make_document(**kwargs))
        assert resp.status_code == 201
        return resp.json()["id"]

    def test_delete_moves_to_trash(self, client):
        doc_id = self._create(client)
        client.delete(f"/api/docs/{doc_id}")

        # Excluded from active list
        docs = client.get("/api/docs").json()
        assert all(d["id"] != doc_id for d in docs)

        # Present in trash
        trash = client.get("/api/docs/trash").json()
        assert any(d["id"] == doc_id for d in trash)

    def test_trash_endpoint_reachable(self, client):
        """Regression: /trash must not be shadowed by /{doc_id}."""
        resp = client.get("/api/docs/trash")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_recent_endpoint_reachable(self, client):
        """Regression: /recent must not be shadowed by /{doc_id}."""
        resp = client.get("/api/docs/recent")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_restore_from_trash(self, client):
        doc_id = self._create(client)
        client.delete(f"/api/docs/{doc_id}")

        resp = client.post(f"/api/docs/{doc_id}/restore")
        assert resp.status_code == 200
        assert resp.json()["id"] == doc_id
        assert resp.json()["deleted_at"] is None

        # Back in active list
        docs = client.get("/api/docs").json()
        assert any(d["id"] == doc_id for d in docs)

        # Gone from trash
        trash = client.get("/api/docs/trash").json()
        assert all(d["id"] != doc_id for d in trash)

    def test_permanent_delete_removes_completely(self, client):
        doc_id = self._create(client)
        client.delete(f"/api/docs/{doc_id}")

        resp = client.delete(f"/api/docs/{doc_id}/permanent")
        assert resp.status_code == 204

        # Gone from trash
        trash = client.get("/api/docs/trash").json()
        assert all(d["id"] != doc_id for d in trash)

        # Gone from active list
        resp = client.get(f"/api/docs/{doc_id}")
        assert resp.status_code == 404

    def test_deleted_doc_excluded_from_search(self, client):
        doc_id = self._create(client, content="unique_softdel_marker_999")
        client.delete(f"/api/docs/{doc_id}")

        results = client.get("/api/docs/search/", params={"q": "unique_softdel_marker_999"}).json()
        assert all(r.get("id") != doc_id for r in results)

    def test_delete_idempotent(self, client):
        doc_id = self._create(client)
        assert client.delete(f"/api/docs/{doc_id}").status_code == 204
        assert client.delete(f"/api/docs/{doc_id}").status_code == 204

    def test_restore_idempotent_on_active_doc(self, client):
        doc_id = self._create(client)
        # Restore an active (non-deleted) doc should succeed
        resp = client.post(f"/api/docs/{doc_id}/restore")
        assert resp.status_code == 200

    def test_permanent_delete_idempotent(self, client):
        doc_id = self._create(client)
        client.delete(f"/api/docs/{doc_id}")
        assert client.delete(f"/api/docs/{doc_id}/permanent").status_code == 204
        # Second call still succeeds (already gone)
        assert client.delete(f"/api/docs/{doc_id}/permanent").status_code == 204

    def test_versions_preserved_after_restore(self, client):
        doc_id = self._create(client)
        # Create a version by updating
        client.put(f"/api/docs/{doc_id}", json={"content": "v2", "author_type": "human"})

        # Soft delete and restore
        client.delete(f"/api/docs/{doc_id}")
        client.post(f"/api/docs/{doc_id}/restore")

        # Versions should still be accessible
        resp = client.get(f"/api/docs/{doc_id}/versions")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    def test_trash_shows_deleted_at_timestamp(self, client):
        doc_id = self._create(client)
        client.delete(f"/api/docs/{doc_id}")

        trash = client.get("/api/docs/trash").json()
        trashed = next(d for d in trash if d["id"] == doc_id)
        assert trashed["deleted_at"] is not None
