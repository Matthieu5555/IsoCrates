"""Database configuration and session management."""

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Database URL - start with SQLite for POC, can switch to PostgreSQL later
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./isocrates.db")


def is_postgresql() -> bool:
    """Check if the configured database is PostgreSQL."""
    return DATABASE_URL.startswith("postgresql")

# Create engine with database-specific tuning.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

    # SQLite defaults foreign_keys to OFF — CASCADE constraints are silently
    # ignored unless we enable them on every connection.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    # PostgreSQL: connection pool sized for typical web workloads.
    # All pool parameters are configurable via DB_POOL_* environment variables.
    from .core.config import settings as _db_settings
    engine = create_engine(
        DATABASE_URL,
        pool_size=_db_settings.db_pool_size,
        max_overflow=_db_settings.db_max_overflow,
        pool_timeout=_db_settings.db_pool_timeout,
        pool_recycle=_db_settings.db_pool_recycle,
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
