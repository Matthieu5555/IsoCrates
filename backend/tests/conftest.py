"""Shared test fixtures for the IsoCrates backend test suite.

All tests use an in-memory SQLite database so they are fast, isolated, and
leave no artefacts. The ``client`` fixture provides a ``TestClient`` wired
to the real FastAPI app with the DB dependency overridden.

Each test gets its own engine and connection via StaticPool, guaranteeing
complete isolation. StaticPool ensures all ORM sessions for that test share
one connection (required for in-memory SQLite).
"""

import os

# Force auth off and use in-memory DB before any app imports.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_ENABLED"] = "false"
os.environ["LOG_FORMAT"] = "text"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.core.token_factory import create_token
from app.core.config import settings
from app.middleware.request_context import _rate_buckets


@pytest.fixture()
def db():
    """Per-test database session on a fresh in-memory database.

    Creates a new engine with StaticPool per test, ensuring complete
    isolation. StaticPool guarantees all connections share one underlying
    SQLite connection (required because in-memory SQLite databases are
    per-connection).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = Session(bind=engine)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def client(db):
    """FastAPI TestClient with the DB dependency overridden to use the test session."""

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    _rate_buckets.clear()  # Reset rate limiter so tests don't hit 429
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers() -> dict:
    """Valid JWT auth headers for write endpoints (when auth is enabled)."""
    token = create_token(
        subject="test-user",
        role="admin",
        secret=settings.jwt_secret_key,
    )
    return {"Authorization": f"Bearer {token}"}


def make_document(
    title: str = "Test Document",
    path: str = "test-crate/docs",
    content: str = "# Test\n\nHello world.",
    **overrides,
) -> dict:
    """Factory for document creation payloads."""
    payload = {
        "title": title,
        "path": path,
        "content": content,
        "repo_url": "https://github.com/test/repo",
        "repo_name": "repo",
        "keywords": [],
        "author_type": "human",
    }
    payload.update(overrides)
    return payload
