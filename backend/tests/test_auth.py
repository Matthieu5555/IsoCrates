"""Tests for the auth module — token creation, validation, and dev mode bypass."""

import time
from app.core.token_factory import create_token, decode_token, TokenPayload
from app.core.config import settings


class TestTokenFactory:

    def test_create_and_decode(self):
        token = create_token("agent", "service", "test-secret")
        payload = decode_token(token, "test-secret")
        assert payload is not None
        assert payload.sub == "agent"
        assert payload.role == "service"

    def test_wrong_secret_returns_none(self):
        token = create_token("agent", "service", "correct-secret")
        assert decode_token(token, "wrong-secret") is None

    def test_expired_token_returns_none(self):
        token = create_token("agent", "service", "secret", expires_hours=-1)
        assert decode_token(token, "secret") is None

    def test_malformed_token_returns_none(self):
        assert decode_token("not.a.token", "secret") is None
        assert decode_token("", "secret") is None


class TestAuthDisabledMode:
    """When AUTH_ENABLED=false (default), write endpoints should succeed without a token."""

    def test_create_without_token_succeeds(self, client):
        resp = client.post("/api/docs", json={
            "title": "No Auth",
            "path": "test",
            "content": "hello",
            "repo_url": "https://github.com/t/r",
            "repo_name": "r",
        })
        assert resp.status_code == 201

    def test_delete_without_token_succeeds(self, client):
        doc_id = client.post("/api/docs", json={
            "title": "To Delete",
            "path": "test",
            "content": "bye",
            "repo_url": "https://github.com/t/r",
            "repo_name": "r",
        }).json()["id"]
        resp = client.delete(f"/api/docs/{doc_id}")
        assert resp.status_code == 204
