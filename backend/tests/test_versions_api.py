"""Tests for the /api/docs/{doc_id}/versions endpoints."""

from tests.conftest import make_document


class TestVersions:

    def test_update_creates_version(self, client):
        doc_id = client.post("/api/docs", json=make_document()).json()["id"]
        client.put(f"/api/docs/{doc_id}", json={"content": "v2", "author_type": "human"})

        resp = client.get(f"/api/docs/{doc_id}/versions")
        assert resp.status_code == 200
        versions = resp.json()
        # Initial creation + one update = 2 versions
        assert len(versions) >= 2

    def test_get_latest_version(self, client):
        doc_id = client.post("/api/docs", json=make_document()).json()["id"]
        client.put(f"/api/docs/{doc_id}", json={"content": "v2 content", "author_type": "human"})

        resp = client.get(f"/api/docs/{doc_id}/versions/latest")
        assert resp.status_code == 200
        version = resp.json()
        assert "content" in version
        assert "version_id" in version
        assert version["doc_id"] == doc_id

    def test_versions_404_for_nonexistent_doc(self, client):
        resp = client.get("/api/docs/doc-nonexistent/versions")
        assert resp.status_code == 404
