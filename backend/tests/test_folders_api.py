"""Tests for folder tree and metadata endpoints."""

from tests.conftest import make_document


class TestTree:

    def test_tree_returns_list(self, client):
        resp = client.get("/api/tree")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_tree_reflects_documents(self, client):
        client.post("/api/docs", json=make_document(path="crate-a/folder", title="Page"))
        resp = client.get("/api/tree")
        tree = resp.json()
        # There should be at least one node
        assert len(tree) >= 1


class TestFolderMetadata:

    def test_create_and_get_folder_metadata(self, client):
        resp = client.post("/api/folders/metadata", json={"path": "test-folder", "description": "A folder"})
        assert resp.status_code == 201
        folder_id = resp.json()["id"]

        get_resp = client.get(f"/api/folders/metadata/{folder_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["path"] == "test-folder"

    def test_duplicate_folder_returns_409(self, client):
        client.post("/api/folders/metadata", json={"path": "dup-folder"})
        resp = client.post("/api/folders/metadata", json={"path": "dup-folder"})
        assert resp.status_code == 409
