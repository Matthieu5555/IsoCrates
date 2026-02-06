"""API routes for personal tree operations.

Every endpoint is scoped to the authenticated user. The user_id is taken
from the auth context, never from the request body — preventing cross-user
access.
"""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.auth import AuthContext, require_auth
from ..database import get_db
from ..exceptions import ForbiddenError
from ..services.personal_tree_service import PersonalTreeService
from ..schemas.personal import (
    PersonalFolderCreate,
    PersonalFolderResponse,
    PersonalFolderMove,
    PersonalDocRefCreate,
    PersonalDocRefResponse,
    PersonalTreeNode,
)

router = APIRouter(prefix="/api/personal", tags=["personal"])


def _verify_folder_owner(service: PersonalTreeService, folder_id: str, user_id: str):
    """Verify the folder belongs to the authenticated user. Raises 403 if not."""
    folder = service.repo.get_folder(folder_id)
    if not folder or folder.user_id != user_id:
        raise ForbiddenError("Folder not found or access denied")


def _verify_ref_owner(service: PersonalTreeService, ref_id: str, user_id: str):
    """Verify the document ref belongs to the authenticated user. Raises 403 if not."""
    ref = service.repo.get_ref(ref_id)
    if not ref or ref.user_id != user_id:
        raise ForbiddenError("Reference not found or access denied")


@router.get("/tree", response_model=List[PersonalTreeNode])
def get_personal_tree(
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Get the full personal tree for the authenticated user."""
    service = PersonalTreeService(db)
    return service.get_tree(auth.user_id)


@router.post("/folders", response_model=PersonalFolderResponse, status_code=201)
def create_personal_folder(
    data: PersonalFolderCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Create a personal folder. Always owned by the authenticated user."""
    service = PersonalTreeService(db)
    return service.create_folder(auth.user_id, data.name, data.parent_id)


@router.delete("/folders/{folder_id}", status_code=204)
def delete_personal_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Delete a personal folder (cascades to children and refs)."""
    service = PersonalTreeService(db)
    _verify_folder_owner(service, folder_id, auth.user_id)
    service.delete_folder(folder_id)


@router.put("/folders/{folder_id}/move", response_model=PersonalFolderResponse)
def move_personal_folder(
    folder_id: str,
    data: PersonalFolderMove,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Move a personal folder to a new parent."""
    service = PersonalTreeService(db)
    _verify_folder_owner(service, folder_id, auth.user_id)
    return service.move_folder(folder_id, data.parent_id)


@router.post("/folders/{folder_id}/refs", response_model=PersonalDocRefResponse, status_code=201)
def add_document_ref(
    folder_id: str,
    data: PersonalDocRefCreate,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Add a document reference to a personal folder."""
    service = PersonalTreeService(db)
    _verify_folder_owner(service, folder_id, auth.user_id)
    return service.add_document_ref(auth.user_id, folder_id, data.document_id)


@router.delete("/refs/{ref_id}", status_code=204)
def remove_document_ref(
    ref_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Remove a document reference."""
    service = PersonalTreeService(db)
    _verify_ref_owner(service, ref_id, auth.user_id)
    service.remove_ref(ref_id)


@router.put("/refs/{ref_id}/move", response_model=PersonalDocRefResponse)
def move_document_ref(
    ref_id: str,
    target_folder_id: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_auth),
):
    """Move a document reference to a different folder."""
    service = PersonalTreeService(db)
    _verify_ref_owner(service, ref_id, auth.user_id)
    _verify_folder_owner(service, target_folder_id, auth.user_id)
    return service.move_ref(ref_id, target_folder_id)
