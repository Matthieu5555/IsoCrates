"""API routes."""

from .documents import router as documents_router
from .versions import router as versions_router
from .dependencies import router as dependencies_router, graph_router
from .folders import router as folders_router, tree_router
from .personal import router as personal_router
from .webhooks import router as webhooks_router
from .jobs import router as jobs_router

__all__ = [
    "documents_router",
    "versions_router",
    "dependencies_router",
    "graph_router",
    "folders_router",
    "tree_router",
    "personal_router",
    "webhooks_router",
    "jobs_router",
]
