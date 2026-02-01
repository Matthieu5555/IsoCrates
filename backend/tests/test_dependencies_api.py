"""Tests for wikilink dependencies — extraction, cycle detection, CRUD."""

from tests.conftest import make_document


class TestDependencies:

    def test_wikilink_extraction_on_save(self, client):
        """Saving content with [[wikilinks]] should create dependency records."""
        # Create target document first
        target = make_document(title="Target Doc", path="crate", repo_name="target-repo")
        target_id = client.post("/api/docs", json=target).json()["id"]

        # Create source with a wikilink
        source = make_document(
            title="Source Doc",
            path="crate",
            content="See [[target-repo]] for details.",
        )
        source_id = client.post("/api/docs", json=source).json()["id"]

        resp = client.get(f"/api/docs/{source_id}/dependencies")
        assert resp.status_code == 200
        deps = resp.json()
        assert "outgoing" in deps
        assert len(deps["outgoing"]) >= 1
        assert any(d["to_doc_id"] == target_id for d in deps["outgoing"])

    def test_get_all_dependencies(self, client):
        resp = client.get("/api/dependencies")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_create_dependency_rejects_self_link(self, client):
        doc_id = client.post("/api/docs", json=make_document()).json()["id"]
        resp = client.post(
            f"/api/docs/{doc_id}/dependencies",
            json={"from_doc_id": doc_id, "to_doc_id": doc_id, "link_type": "wikilink"},
        )
        assert resp.status_code == 400


class TestBrokenLinks:

    def test_broken_links_all_resolved(self, client):
        """When all wikilinks resolve, broken-links returns all resolved=True."""
        target = make_document(title="Linked", path="crate", repo_name="linked-repo")
        client.post("/api/docs", json=target)

        source = make_document(
            title="Src", path="crate",
            content="Link to [[linked-repo]].",
        )
        source_id = client.post("/api/docs", json=source).json()["id"]

        resp = client.get(f"/api/docs/{source_id}/broken-links")
        assert resp.status_code == 200
        links = resp.json()
        assert len(links) == 1
        assert links[0]["target"] == "linked-repo"
        assert links[0]["resolved"] is True

    def test_broken_links_with_unresolved(self, client):
        """Wikilink to nonexistent target is reported as unresolved."""
        doc = make_document(
            title="Has Links", path="broken-test",
            content="See [[xq9]] here.",
            repo_name="broken-test-repo",
        )
        doc_id = client.post("/api/docs", json=doc).json()["id"]

        resp = client.get(f"/api/docs/{doc_id}/broken-links")
        assert resp.status_code == 200
        links = resp.json()
        assert len(links) == 1
        assert links[0]["target"] == "xq9"
        assert links[0]["resolved"] is False
        assert links[0]["resolved_doc_id"] is None

    def test_broken_links_empty_for_no_wikilinks(self, client):
        """Document with no wikilinks returns empty list."""
        doc = make_document(title="Plain", path="crate", content="No links here.")
        doc_id = client.post("/api/docs", json=doc).json()["id"]

        resp = client.get(f"/api/docs/{doc_id}/broken-links")
        assert resp.status_code == 200
        assert resp.json() == []


class TestWikilinkResolution:

    def test_resolve_wikilink_endpoint(self, client):
        """GET /resolve/ returns correct doc ID for a known target."""
        doc = make_document(title="Resolvable", path="crate", repo_name="resolvable-repo")
        doc_id = client.post("/api/docs", json=doc).json()["id"]

        resp = client.get("/api/docs/resolve/", params={"target": "resolvable-repo"})
        assert resp.status_code == 200
        assert resp.json()["doc_id"] == doc_id

    def test_resolve_wikilink_not_found(self, client):
        """GET /resolve/ returns 404 for unknown target."""
        resp = client.get("/api/docs/resolve/", params={"target": "nonexistent-target-abc"})
        assert resp.status_code == 404


class TestCircularDependencies:

    def test_wikilink_circular_dependency_allowed(self, client):
        """Wikilinks are cross-references — A→B then B→A should be allowed."""
        a_id = client.post("/api/docs", json=make_document(title="A", path="crate/a")).json()["id"]
        b_id = client.post("/api/docs", json=make_document(title="B", path="crate/b")).json()["id"]

        # Create A→B
        resp = client.post(
            f"/api/docs/{a_id}/dependencies",
            json={"from_doc_id": a_id, "to_doc_id": b_id, "link_type": "wikilink"},
        )
        assert resp.status_code == 201

        # B→A should be allowed for wikilinks
        resp = client.post(
            f"/api/docs/{b_id}/dependencies",
            json={"from_doc_id": b_id, "to_doc_id": a_id, "link_type": "wikilink"},
        )
        assert resp.status_code == 201

    def test_non_wikilink_circular_dependency_rejected(self, client):
        """Non-wikilink dependency types still reject cycles."""
        a_id = client.post("/api/docs", json=make_document(title="CycA", path="crate/ca")).json()["id"]
        b_id = client.post("/api/docs", json=make_document(title="CycB", path="crate/cb")).json()["id"]

        resp = client.post(
            f"/api/docs/{a_id}/dependencies",
            json={"from_doc_id": a_id, "to_doc_id": b_id, "link_type": "import"},
        )
        assert resp.status_code == 201

        resp = client.post(
            f"/api/docs/{b_id}/dependencies",
            json={"from_doc_id": b_id, "to_doc_id": a_id, "link_type": "import"},
        )
        assert resp.status_code == 400


class TestDependencyRefresh:

    def test_dependencies_refreshed_on_update(self, client):
        """Updating content should add/remove dependencies accordingly."""
        target = make_document(title="Dep Target", path="crate", repo_name="dep-target")
        target_id = client.post("/api/docs", json=target).json()["id"]

        # Create doc without wikilinks
        doc = make_document(title="Updatable", path="crate", content="No links.")
        doc_id = client.post("/api/docs", json=doc).json()["id"]

        deps = client.get(f"/api/docs/{doc_id}/dependencies").json()
        assert len(deps["outgoing"]) == 0

        # Update to add a wikilink
        client.put(f"/api/docs/{doc_id}", json={
            "content": "Now links to [[dep-target]].",
            "author_type": "human",
        })

        deps = client.get(f"/api/docs/{doc_id}/dependencies").json()
        assert len(deps["outgoing"]) >= 1
        assert any(d["to_doc_id"] == target_id for d in deps["outgoing"])

        # Update to remove the wikilink
        client.put(f"/api/docs/{doc_id}", json={
            "content": "Links removed.",
            "author_type": "human",
        })

        deps = client.get(f"/api/docs/{doc_id}/dependencies").json()
        assert len(deps["outgoing"]) == 0
