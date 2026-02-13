"""Database configuration and session management.

PostgreSQL is the only supported database. The connection URL must be set via
DATABASE_URL in the environment or .env file.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Single source of truth: pydantic settings (reads from env vars + .env file).
# No silent fallback — if DATABASE_URL is missing, Settings() raises immediately.
from .core.config import settings as _settings

DATABASE_URL = _settings.database_url

# PostgreSQL connection pool sized for typical web workloads.
# All pool parameters are configurable via DB_POOL_* environment variables.
engine = create_engine(
    DATABASE_URL,
    pool_size=_settings.db_pool_size,
    max_overflow=_settings.db_max_overflow,
    pool_timeout=_settings.db_pool_timeout,
    pool_recycle=_settings.db_pool_recycle,
    # Detects stale connections before use (prevents "server closed the connection" errors).
    pool_pre_ping=True,
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()


def get_db():
    """Dependency for FastAPI routes to get database session.

    Rolls back the transaction on unhandled exceptions so that the
    connection is returned to the pool in a clean state.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
