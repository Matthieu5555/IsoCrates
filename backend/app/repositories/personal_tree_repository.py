"""Repository for personal tree CRUD operations."""

import hashlib
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from ..models.personal import PersonalFolder, PersonalDocumentRef


class PersonalTreeRepository:
    """CRUD for personal_folders and personal_document_refs."""

    def __init__(self, db: Session):
        self.db = db

    # --- Folders ---

    def create_folder(self, user_id: str, name: str, parent_id: Optional[str] = None) -> PersonalFolder:
        folder_id = self._generate_folder_id(user_id, name, parent_id)
        folder = PersonalFolder(
            folder_id=folder_id,
            user_id=user_id,
            name=name,
            parent_id=parent_id,
            sort_order=0,
        )
        self.db.add(folder)
        self.db.commit()
        self.db.refresh(folder)
        return folder

    def get_folder(self, folder_id: str) -> Optional[PersonalFolder]:
        return self.db.query(PersonalFolder).filter(PersonalFolder.folder_id == folder_id).first()

    def get_folders_by_user(self, user_id: str) -> List[PersonalFolder]:
        return (
            self.db.query(PersonalFolder)
            .filter(PersonalFolder.user_id == user_id)
            .order_by(PersonalFolder.sort_order, PersonalFolder.name)
            .all()
        )

    def get_children(self, folder_id: str) -> List[PersonalFolder]:
        return (
            self.db.query(PersonalFolder)
            .filter(PersonalFolder.parent_id == folder_id)
            .order_by(PersonalFolder.sort_order, PersonalFolder.name)
            .all()
        )

    def move_folder(self, folder_id: str, new_parent_id: Optional[str]) -> Optional[PersonalFolder]:
        folder = self.get_folder(folder_id)
        if not folder:
            return None
        folder.parent_id = new_parent_id
        self.db.commit()
        self.db.refresh(folder)
        return folder

    def delete_folder(self, folder_id: str) -> bool:
        folder = self.get_folder(folder_id)
        if not folder:
            return False
        self.db.delete(folder)
        self.db.commit()
        return True

    # --- Document refs ---

    def create_ref(self, user_id: str, folder_id: str, document_id: str) -> PersonalDocumentRef:
        ref_id = self._generate_ref_id(user_id, folder_id, document_id)
        ref = PersonalDocumentRef(
            ref_id=ref_id,
            user_id=user_id,
            folder_id=folder_id,
            document_id=document_id,
            sort_order=0,
        )
        self.db.add(ref)
        self.db.commit()
        self.db.refresh(ref)
        return ref

    def get_ref(self, ref_id: str) -> Optional[PersonalDocumentRef]:
        return self.db.query(PersonalDocumentRef).filter(PersonalDocumentRef.ref_id == ref_id).first()

    def get_refs_by_folder(self, folder_id: str) -> List[PersonalDocumentRef]:
        return (
            self.db.query(PersonalDocumentRef)
            .filter(PersonalDocumentRef.folder_id == folder_id)
            .order_by(PersonalDocumentRef.sort_order)
            .all()
        )

    def get_refs_by_user(self, user_id: str) -> List[PersonalDocumentRef]:
        return (
            self.db.query(PersonalDocumentRef)
            .filter(PersonalDocumentRef.user_id == user_id)
            .order_by(PersonalDocumentRef.sort_order)
            .all()
        )

    def find_existing_ref(self, user_id: str, folder_id: str, document_id: str) -> Optional[PersonalDocumentRef]:
        return (
            self.db.query(PersonalDocumentRef)
            .filter(
                PersonalDocumentRef.user_id == user_id,
                PersonalDocumentRef.folder_id == folder_id,
                PersonalDocumentRef.document_id == document_id,
            )
            .first()
        )

    def move_ref(self, ref_id: str, target_folder_id: str) -> Optional[PersonalDocumentRef]:
        ref = self.get_ref(ref_id)
        if not ref:
            return None
        ref.folder_id = target_folder_id
        self.db.commit()
        self.db.refresh(ref)
        return ref

    def delete_ref(self, ref_id: str) -> bool:
        ref = self.get_ref(ref_id)
        if not ref:
            return False
        self.db.delete(ref)
        self.db.commit()
        return True

    # --- Helpers ---

    @staticmethod
    def _generate_folder_id(user_id: str, name: str, parent_id: Optional[str]) -> str:
        raw = f"{user_id}:{parent_id or 'root'}:{name}"
        h = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pf-{h}"

    @staticmethod
    def _generate_ref_id(user_id: str, folder_id: str, document_id: str) -> str:
        raw = f"{user_id}:{folder_id}:{document_id}"
        h = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return f"pr-{h}"
