from __future__ import annotations

from typing import BinaryIO

from ..auth import CurrentUser
from ..models import AssetKind
from ..repositories import WorkbenchRepository
from ..storage import LocalStorage


class AssetService:
    def __init__(self, repo: WorkbenchRepository, storage: LocalStorage):
        self.repo = repo
        self.storage = storage

    def upload_asset(
        self,
        *,
        user: CurrentUser,
        kind: AssetKind,
        filename: str,
        mime_type: str,
        stream: BinaryIO,
        folder_id: int | None,
        project_id: int | None = None,
    ) -> dict:
        stored = self.storage.store_asset(kind, filename, stream)
        return self.repo.create_asset(
            project_id=project_id,
            kind=kind,
            original_filename=filename,
            storage_key=stored.storage_key,
            mime_type=mime_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            uploaded_by=user.id,
            folder_id=folder_id,
        )

    def list_assets(
        self,
        kind: str | None = None,
        user_id: int | None = None,
        role: str | None = None,
        project_id: int | None = None,
    ) -> list[dict]:
        return self.repo.list_assets(kind=kind, user_id=user_id, role=role, project_id=project_id)
