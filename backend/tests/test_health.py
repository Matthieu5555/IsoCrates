"""Tests for /health and / endpoints."""


class TestHealth:

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert "db" in data
        assert "uptime_seconds" in data
        assert "version" in data
        assert "document_count" in data

    def test_root_returns_api_info(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["name"] == "IsoCrates API"


class TestResponseHeaders:

    def test_response_includes_middleware_headers(self, client):
        resp = client.get("/health")
        assert "x-request-id" in resp.headers
        assert "x-response-time" in resp.headers
