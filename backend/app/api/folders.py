"""Folder API: metadata CRUD, move, delete, tree, and cleanup.

Single router for all folder operations. Delegates to FolderService (deep module).
Tree endpoint filters nodes by the user's folder grants.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..core.auth import AuthContext, require_auth, optional_auth
from ..database import get_db
from ..schemas.folder import (
    FolderMetadataCreate,
    FolderMetadataUpdate,
    FolderMetadataResponse,
    FolderMoveRequest,
    FolderOperationResponse,
    TreeNode,
)
from ..services.folder_service import FolderService
from ..services.permission_service import check_permission, filter_paths_by_grants
from ..exceptions import ForbiddenError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/folders", tags=["folders"])

# Separate router to keep /api/tree at its existing URL (consumed by frontend).
tree_router = APIRouter(tags=["folders"])


# -- Tree -----------------------------------------------------------------

@tree_router.get("/api/tree", response_model=List[TreeNode])
def get_tree(
    db: Session = Depends(get_db),
    auth: Optional[AuthContext] = Depends(optional_auth),
):
    """Get hierarchical navigation tree, filtered by user's folder grants."""
    service = FolderService(db)
    allowed_prefixes = filter_paths_by_grants(auth.grants) if auth is not None else None
    return service.get_tree(allowed_prefixes=allowed_prefixes)


# -- Folder metadata CRUD ------------------------------------------------

@router.post("/metadata", response_model=FolderMetadataResponse, status_code=201)
def create_folder_metadata(
    data: FolderMetadataCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Create metadata for a folder (idempotent at service level)."""
    if not check_permission(auth.grants, data.path, "edit"):
        raise ForbiddenError("No edit access to this path")

    service = FolderService(db)
    existing = service.get_folder_by_path(data.path)
    if existing:
        raise HTTPException(status_code=409, detail=f"Folder already exists: {data.path}")

    folder = service.create_folder(data)
    return folder


@router.get("/metadata/{folder_id}", response_model=FolderMetadataResponse)
def get_folder_metadata(folder_id: str, db: Session = Depends(get_db)):
    service = FolderService(db)
    folder = service.get_folder(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder metadata not found: {folder_id}")
    return folder


@router.get("/metadata", response_model=List[FolderMetadataResponse])
def list_folder_metadata(
    path_prefix: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    service = FolderService(db)
    return service.list_folders(path_prefix)


@router.put("/metadata/{folder_id}", response_model=FolderMetadataResponse)
def update_folder_metadata(
    folder_id: str,
    data: FolderMetadataUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    service = FolderService(db)
    folder = service.get_folder(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder metadata not found: {folder_id}")

    folder_path = getattr(folder, "path", "")
    if not check_permission(auth.grants, folder_path, "edit"):
        raise ForbiddenError("No edit access to this folder")

    updated = service.update_folder(folder_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Folder metadata not found: {folder_id}")
    return updated


# -- Folder operations ----------------------------------------------------

@router.put("/move", response_model=FolderOperationResponse)
def move_folder(
    request: FolderMoveRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Move a folder to a new location. Requires edit on both source and target."""
    if not check_permission(auth.grants, request.source_path, "edit"):
        raise ForbiddenError("No edit access to source path")
    if not check_permission(auth.grants, request.target_path, "edit"):
        raise ForbiddenError("No edit access to target path")

    try:
        service = FolderService(db)
        return service.move_folder(request.source_path, request.target_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{folder_path:path}", response_model=FolderOperationResponse)
def delete_folder(
    folder_path: str,
    action: str = "move_up",
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Delete a folder. action='move_up' or 'delete_all'."""
    if action not in ("move_up", "delete_all"):
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    if not check_permission(auth.grants, folder_path, "delete"):
        raise ForbiddenError("No delete access to this folder")

    try:
        service = FolderService(db)
        return service.delete_folder(folder_path, action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# -- Cleanup --------------------------------------------------------------

@router.post("/cleanup", response_model=dict)
def cleanup_orphan_metadata(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Remove folder metadata for paths that no longer have any documents."""
    if not auth.is_admin:
        raise ForbiddenError("Admin access required for cleanup")
    service = FolderService(db)
    count = service.cleanup_orphans()
    return {"deleted_count": count}
