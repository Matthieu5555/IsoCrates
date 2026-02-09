"""Main FastAPI application."""

import logging
import sys
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import engine, Base, get_db, SessionLocal, DATABASE_URL
from .api import documents_router, versions_router, tree_router, dependencies_router, graph_router, folders_router, personal_router, webhooks_router, jobs_router
from .api.auth_routes import router as auth_router
from .core.config import settings, ConfigurationError, Environment
from .core.logging_config import setup_logging
from .middleware.exception_handler import iso_exception_handler
from .middleware.request_context import RequestContextMiddleware
from .exceptions import IsoException
from .services import DocumentService
from .services import audit_service

# Setup logging first
setup_logging(log_level=settings.log_level, log_format=settings.log_format)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Startup validation: verify database connectivity before attempting anything
# else. Gives clear, actionable error messages when things fail.
# ---------------------------------------------------------------------------

def _mask_url(url: str) -> str:
    """Mask password in database URL for safe logging."""
    # postgresql://user:password@host/db -> postgresql://user:***@host/db
    import re
    return re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', url)


def _validate_database_connection() -> None:
    """Test that the database is reachable. Exits with clear message on failure."""
    masked = _mask_url(DATABASE_URL)
    logger.info(f"Connecting to database: {masked}")

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception as e:
        error_str = str(e)

        if DATABASE_URL.startswith("postgresql"):
            if "could not connect" in error_str or "Connection refused" in error_str:
                logger.critical(
                    "Cannot connect to PostgreSQL.\n"
                    f"  DATABASE_URL: {masked}\n"
                    "  Possible fixes:\n"
                    "    1. Verify PostgreSQL is running: pg_isready -h <host> -p <port>\n"
                    "    2. Check DATABASE_URL in .env or environment variables\n"
                    "    3. If using Docker Compose: docker compose up -d postgres\n"
                    f"  Error: {error_str}"
                )
            elif "authentication failed" in error_str or "password" in error_str.lower():
                logger.critical(
                    "PostgreSQL authentication failed.\n"
                    f"  DATABASE_URL: {masked}\n"
                    "  Possible fixes:\n"
                    "    1. Check username and password in DATABASE_URL\n"
                    "    2. Verify pg_hba.conf allows this connection method\n"
                    f"  Error: {error_str}"
                )
            elif "does not exist" in error_str:
                logger.critical(
                    "PostgreSQL database does not exist.\n"
                    f"  DATABASE_URL: {masked}\n"
                    "  Fix: createdb <database_name>\n"
                    f"  Error: {error_str}"
                )
            else:
                logger.critical(
                    f"PostgreSQL connection failed.\n"
                    f"  DATABASE_URL: {masked}\n"
                    f"  Error: {error_str}"
                )
        elif DATABASE_URL.startswith("sqlite"):
            logger.critical(
                f"SQLite database error.\n"
                f"  DATABASE_URL: {masked}\n"
                "  Check that the directory exists and is writable.\n"
                f"  Error: {error_str}"
            )
        else:
            logger.critical(
                f"Database connection failed.\n"
                f"  DATABASE_URL: {masked}\n"
                f"  Error: {error_str}"
            )
        raise SystemExit(1)


_validate_database_connection()

# Run database migrations (handles both fresh installs and updates)
from .core.migrator import run_migrations, MigrationError

try:
    result = run_migrations(engine, Base)
    if result.applied > 0:
        logger.info(f"Applied {result.applied} database migration(s)")
    elif result.baselined > 0:
        logger.info(f"Fresh install: baselined {result.baselined} migrations")
    else:
        logger.debug("No pending migrations")
except MigrationError as e:
    logger.critical(f"Database migration failed: {e}")
    raise SystemExit(1) from e

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle for the IsoCrates API."""
    # --- Security validation ---
    logger.info(f"Environment: {settings.environment.value}")
    try:
        settings.validate_production_config()
    except ConfigurationError as e:
        logger.critical(f"STARTUP BLOCKED: {e}")
        raise SystemExit(1) from e

    if settings.environment == Environment.DEVELOPMENT:
        if settings.jwt_secret_key == "dev-insecure-key-change-me":
            if settings.auth_enabled:
                logger.critical(
                    "SECURITY: AUTH_ENABLED=true but JWT_SECRET_KEY is the default. "
                    "Anyone can forge tokens. Generate a secure key: openssl rand -hex 32"
                )
            else:
                logger.warning(
                    "SECURITY: JWT_SECRET_KEY is the default. "
                    "Set a secure key before enabling auth: openssl rand -hex 32"
                )

        if not settings.auth_enabled:
            logger.warning(
                "SECURITY: Authentication is disabled (AUTH_ENABLED=false). "
                "All write endpoints are unprotected. Set AUTH_ENABLED=true for production."
            )

        if not settings.github_webhook_secret:
            logger.warning(
                "SECURITY: GITHUB_WEBHOOK_SECRET is empty. "
                "Webhook signature verification is disabled."
            )

        origins = settings.get_cors_origins()
        localhost_origins = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
        if localhost_origins:
            logger.warning(
                "CORS allows localhost origins: %s. Remove these for production.",
                localhost_origins,
            )

    # --- Seed initial documents (first startup only) ---
    from .core.seeder import seed_initial_documents
    db = SessionLocal()
    try:
        seeded = seed_initial_documents(db)
        if seeded > 0:
            logger.info(f"First startup: seeded {seeded} documents")
    except Exception as e:
        logger.warning(f"Seed loading failed (non-fatal): {e}")
    finally:
        db.close()

    # --- Purge expired trash ---
    db = SessionLocal()
    try:
        purged = DocumentService(db).purge_expired_trash()
        if purged > 0:
            logger.info(f"Purged {purged} expired documents from trash")
    except Exception as e:
        logger.warning(f"Trash purge failed (non-fatal): {e}")
    finally:
        db.close()

    # --- Purge old audit logs ---
    if settings.audit_retention_days > 0:
        db = SessionLocal()
        try:
            purged = audit_service.purge_old_entries(db, days=settings.audit_retention_days)
            if purged > 0:
                logger.info(f"Purged {purged} audit log entries older than {settings.audit_retention_days} days")
        except Exception as e:
            logger.warning(f"Audit log purge failed (non-fatal): {e}")
        finally:
            db.close()

    yield  # App runs here

    # Shutdown: nothing to clean up currently


# Create FastAPI app
app = FastAPI(
    title="IsoCrates API",
    description=(
        "REST API for the IsoCrates technical documentation platform. "
        "Provides document CRUD with hierarchical folder organisation, "
        "version tracking, wikilink dependency graphs, and AI-generated content management.\n\n"
        "**Authentication:** When `AUTH_ENABLED=true`, all write endpoints require a "
        "`Bearer` token in the `Authorization` header. Read endpoints accept tokens optionally. "
        "When `AUTH_ENABLED=false` (default), all endpoints are open."
    ),
    version="1.0.0",
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    lifespan=lifespan,
)

# Middleware stack (outermost first — CORS wraps request context).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
app.add_middleware(RequestContextMiddleware)

# Register exception handlers
app.add_exception_handler(IsoException, iso_exception_handler)

# Log startup summary — gives deployers a quick overview of what's configured.
db_type = "PostgreSQL" if DATABASE_URL.startswith("postgresql") else "SQLite"
logger.info(
    "IsoCrates API started | env=%s | db=%s | auth=%s | cors=%s",
    settings.environment.value,
    db_type,
    "enabled" if settings.auth_enabled else "disabled",
    ",".join(settings.get_cors_origins()),
)

# Include routers
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(versions_router)
app.include_router(dependencies_router)
app.include_router(graph_router)
app.include_router(folders_router)
app.include_router(tree_router)
app.include_router(personal_router)
app.include_router(webhooks_router)
app.include_router(jobs_router)


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "name": "IsoCrates API",
        "version": "1.0.0",
        "status": "running"
    }


_startup_time = time.monotonic()


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint returning database status, uptime, and document count.

    Never raises — returns degraded status on DB failure so load balancers
    can still probe without receiving 5xx.
    """
    db_status = "ok"
    document_count = 0
    try:
        db.execute(text("SELECT 1"))
        row = db.execute(text("SELECT COUNT(*) FROM documents")).scalar()
        document_count = row or 0
    except Exception:
        db_status = "error"

    return {
        "status": "healthy" if db_status == "ok" else "degraded",
        "db": db_status,
        "uptime_seconds": round(time.monotonic() - _startup_time),
        "version": "1.0.0",
        "document_count": document_count,
    }
