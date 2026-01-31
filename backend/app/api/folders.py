"""Folder API: metadata CRUD, move, delete, tree, and cleanup.

Single router for all folder operations. Delegates to FolderService (deep module).
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..core.auth import require_auth
from ..core.token_factory import TokenPayload
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/folders", tags=["folders"])

# Separate router to keep /api/tree at its existing URL (consumed by frontend).
tree_router = APIRouter(tags=["folders"])


# -- Tree -----------------------------------------------------------------

@tree_router.get("/api/tree", response_model=List[TreeNode])
def get_tree(db: Session = Depends(get_db)):
    """Get hierarchical navigation tree."""
    service = FolderService(db)
    return service.get_tree()


# -- Folder metadata CRUD ------------------------------------------------

@router.post("/metadata", response_model=FolderMetadataResponse, status_code=201)
def create_folder_metadata(data: FolderMetadataCreate, db: Session = Depends(get_db), auth: TokenPayload = Depends(require_auth)):
    """Create metadata for a folder (idempotent at service level).

    Returns 409 if the folder already exists so the frontend can distinguish.
    """
    service = FolderService(db)
    existing = service.get_folder_by_path(data.path)
    if existing:
        raise HTTPException(status_code=409, detail=f"Folder already exists: {data.path}")

    try:
        folder = service.create_folder(data)
        return folder
    except Exception as e:
        logger.error(f"Failed to create folder: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    auth: TokenPayload = Depends(require_auth),
):
    service = FolderService(db)
    folder = service.update_folder(folder_id, data)
    if not folder:
        raise HTTPException(status_code=404, detail=f"Folder metadata not found: {folder_id}")
    return folder


# -- Folder operations ----------------------------------------------------

@router.put("/move", response_model=FolderOperationResponse)
def move_folder(request: FolderMoveRequest, db: Session = Depends(get_db), auth: TokenPayload = Depends(require_auth)):
    """Move a folder to a new location."""
    try:
        service = FolderService(db)
        return service.move_folder(request.source_path, request.target_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to move folder: {str(e)}")


@router.delete("/{folder_path:path}", response_model=FolderOperationResponse)
def delete_folder(
    folder_path: str,
    action: str = "move_up",
    db: Session = Depends(get_db),
    auth: TokenPayload = Depends(require_auth),
):
    """Delete a folder. action='move_up' or 'delete_all'."""
    if action not in ("move_up", "delete_all"):
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    try:
        service = FolderService(db)
        return service.delete_folder(folder_path, action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete folder {folder_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete folder: {str(e)}")


# -- Cleanup --------------------------------------------------------------

@router.post("/cleanup", response_model=dict)
def cleanup_orphan_metadata(db: Session = Depends(get_db), auth: TokenPayload = Depends(require_auth)):
    """Remove folder metadata for paths that no longer have any documents."""
    service = FolderService(db)
    count = service.cleanup_orphans()
    return {"deleted_count": count}
