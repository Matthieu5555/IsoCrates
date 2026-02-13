"""Shared test fixtures for the IsoCrates backend test suite.

All tests use a PostgreSQL test database (isocrates_test). Each test gets
a clean database via TRUNCATE, ensuring complete isolation.

The app's migrator handles table creation and migrations automatically on
import, so no explicit create_all is needed here.

Requires: a local PostgreSQL with the isocrates_test database created:
  createdb -U isocrates isocrates_test
  psql -U superuser isocrates_test -c "CREATE EXTENSION IF NOT EXISTS vector;"
"""

import os

# Force auth off and use the test database before any app imports.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://isocrates:isocrates@localhost:5432/isocrates_test",
)
os.environ["AUTH_ENABLED"] = "false"
os.environ["LOG_FORMAT"] = "text"

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from app.database import Base, get_db, engine, SessionLocal
from app.main import app
from app.core.token_factory import create_token
from app.core.config import settings
from app.middleware.request_context import _rate_buckets

# Tables to truncate between tests (order matters for foreign keys).
_TRUNCATE_TABLES = [
    "personal_document_refs", "personal_folders",
    "dependencies", "versions", "folder_grants", "folder_metadata",
    "generation_jobs", "audit_log", "documents",
]


@pytest.fixture(autouse=True)
def _clean_tables():
    """Truncate all data tables before each test for isolation.

    Uses TRUNCATE CASCADE which is fast and resets sequences.
    Runs before the test (not after) so test failures leave data
    available for debugging.
    """
    db = SessionLocal()
    try:
        db.execute(text(
            f"TRUNCATE {', '.join(_TRUNCATE_TABLES)} RESTART IDENTITY CASCADE"
        ))
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture()
def db():
    """Per-test database session."""
    session = SessionLocal()
    yield session
    session.close()


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
