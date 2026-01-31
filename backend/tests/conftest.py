"""Shared test fixtures for the IsoCrates backend test suite.

All tests use an in-memory SQLite database so they are fast, isolated, and
leave no artefacts. The ``client`` fixture provides a ``TestClient`` wired
to the real FastAPI app with the DB dependency overridden.
"""

import os

# Force auth off and use in-memory DB before any app imports.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_ENABLED"] = "false"
os.environ["LOG_FORMAT"] = "text"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.main import app
from app.core.token_factory import create_token
from app.core.config import settings


@pytest.fixture(scope="session")
def engine():
    """In-memory SQLite engine shared across the test session."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture()
def db(engine):
    """Per-test database session. Rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection)
    session = TestSession()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """FastAPI TestClient with the DB dependency overridden to use the test session."""

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
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
