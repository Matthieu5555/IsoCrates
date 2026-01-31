"""API routes for personal tree operations."""

from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.auth import require_auth
from ..core.token_factory import TokenPayload
from ..database import get_db
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


@router.get("/tree", response_model=List[PersonalTreeNode])
def get_personal_tree(user_id: str = "default", db: Session = Depends(get_db)):
    """Get the full personal tree for a user."""
    service = PersonalTreeService(db)
    return service.get_tree(user_id)


@router.post("/folders", response_model=PersonalFolderResponse, status_code=201)
def create_personal_folder(data: PersonalFolderCreate, db: Session = Depends(get_db), auth: TokenPayload = Depends(require_auth)):
    """Create a personal folder."""
    service = PersonalTreeService(db)
    return service.create_folder(data.user_id, data.name, data.parent_id)


@router.delete("/folders/{folder_id}", status_code=204)
def delete_personal_folder(folder_id: str, db: Session = Depends(get_db), auth: TokenPayload = Depends(require_auth)):
    """Delete a personal folder (cascades to children and refs)."""
    service = PersonalTreeService(db)
    service.delete_folder(folder_id)


@router.put("/folders/{folder_id}/move", response_model=PersonalFolderResponse)
def move_personal_folder(folder_id: str, data: PersonalFolderMove, db: Session = Depends(get_db), auth: TokenPayload = Depends(require_auth)):
    """Move a personal folder to a new parent."""
    service = PersonalTreeService(db)
    return service.move_folder(folder_id, data.parent_id)


@router.post("/folders/{folder_id}/refs", response_model=PersonalDocRefResponse, status_code=201)
def add_document_ref(folder_id: str, data: PersonalDocRefCreate, db: Session = Depends(get_db), auth: TokenPayload = Depends(require_auth)):
    """Add a document reference to a personal folder."""
    service = PersonalTreeService(db)
    return service.add_document_ref(data.user_id, folder_id, data.document_id)


@router.delete("/refs/{ref_id}", status_code=204)
def remove_document_ref(ref_id: str, db: Session = Depends(get_db), auth: TokenPayload = Depends(require_auth)):
    """Remove a document reference."""
    service = PersonalTreeService(db)
    service.remove_ref(ref_id)


@router.put("/refs/{ref_id}/move", response_model=PersonalDocRefResponse)
def move_document_ref(ref_id: str, target_folder_id: str, db: Session = Depends(get_db), auth: TokenPayload = Depends(require_auth)):
    """Move a document reference to a different folder."""
    service = PersonalTreeService(db)
    return service.move_ref(ref_id, target_folder_id)
