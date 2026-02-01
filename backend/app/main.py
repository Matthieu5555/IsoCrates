"""Main FastAPI application."""

import logging
import time

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import engine, Base, get_db, SessionLocal
from .api import documents_router, versions_router, tree_router, dependencies_router, graph_router, folders_router, personal_router, webhooks_router, jobs_router
from .api.auth_routes import router as auth_router
from .core.config import settings
from .core.logging_config import setup_logging
from .middleware.exception_handler import iso_exception_handler
from .middleware.request_context import RequestContextMiddleware
from .exceptions import IsoException
from .services import DocumentService

# Setup logging first
setup_logging(log_level=settings.log_level, log_format=settings.log_format)
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

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
    license_info={"name": "Proprietary"},
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

# Log startup
logger.info("IsoCrates API started successfully")
logger.info(f"CORS allowed origins: {settings.get_cors_origins()}")
logger.info(f"Database: {settings.database_url}")

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


@app.on_event("startup")
def check_security_config():
    """Warn about insecure configuration at startup."""
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


@app.on_event("startup")
def purge_expired_trash():
    """Remove documents that have been in trash for over 30 days."""
    db = SessionLocal()
    try:
        purged = DocumentService(db).purge_expired_trash()
        if purged > 0:
            logger.info(f"Purged {purged} expired documents from trash")
    except Exception as e:
        logger.warning(f"Trash purge failed (non-fatal): {e}")
    finally:
        db.close()


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
