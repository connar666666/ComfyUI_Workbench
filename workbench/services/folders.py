from __future__ import annotations

import sqlite3
from typing import Any, Literal

from ..auth import CurrentUser
from ..errors import ConflictError, ValidationError
from ..repositories import WorkbenchRepository


FolderScope = Literal["assets", "videos"]
_VALID_SCOPES: tuple[FolderScope, ...] = ("assets", "videos")
_NAME_MAX = 64


class FolderService:
    def __init__(self, repo: WorkbenchRepository):
        self.repo = repo

    def list_folders(
        self,
        *,
        scope: FolderScope = "assets",
        parent_id: int | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_scope(scope)
        return self.repo.list_folders(scope=scope, parent_id=parent_id)

    def create_folder(
        self,
        *,
        user: CurrentUser,
        scope: FolderScope = "assets",
        name: str,
        parent_id: int | None = None,
    ) -> dict[str, Any]:
        self._validate_scope(scope)
        clean_name = self._validate_name(name)
        if parent_id is not None:
            self._get_folder_or_raise(parent_id, scope=scope)
        if self.repo.find_folder_by_name(
            scope=scope, name=clean_name, parent_id=parent_id,
        ) is not None:
            raise ConflictError(
                f"a folder named '{clean_name}' already exists in this location"
            )
        try:
            folder_id = self.repo.create_folder(
                scope=scope,
                name=clean_name,
                parent_id=parent_id,
                created_by=user.id,
            )
        except sqlite3.IntegrityError as exc:
            raise ConflictError(
                f"a folder named '{clean_name}' already exists in this location"
            ) from exc
        return self.repo.get_folder(folder_id)

    def rename_folder(self, *, user: CurrentUser, folder_id: int, name: str) -> dict[str, Any]:
        clean_name = self._validate_name(name)
        existing = self.repo.get_folder(folder_id)
        if existing["scope"] != "assets":
            raise ValidationError("folder rename is only supported for assets scope")
        if self.repo.find_folder_by_name(
            scope=existing["scope"],
            name=clean_name,
            parent_id=existing["parent_id"],
            exclude_id=folder_id,
        ) is not None:
            raise ConflictError(
                f"a folder named '{clean_name}' already exists in this location"
            )
        try:
            self.repo.rename_folder(folder_id, clean_name)
        except sqlite3.IntegrityError as exc:
            raise ConflictError(
                f"a folder named '{clean_name}' already exists in this location"
            ) from exc
        return self.repo.get_folder(folder_id)

    def delete_folder(self, *, user: CurrentUser, folder_id: int) -> None:
        folder = self.repo.get_folder(folder_id)
        if folder["scope"] != "assets":
            raise ValidationError("folder delete is only supported for assets scope")
        asset_count = self.repo.count_assets_in_folder(folder_id)
        child_count = self.repo.count_child_folders(folder_id)
        if asset_count > 0:
            raise ConflictError(
                f"folder contains {asset_count} asset(s); move or delete them first"
            )
        if child_count > 0:
            raise ConflictError(
                f"folder contains {child_count} sub-folder(s); remove them first"
            )
        self.repo.delete_folder(folder_id)

    @staticmethod
    def _validate_scope(scope: str) -> None:
        if scope not in _VALID_SCOPES:
            raise ValidationError(
                f"unsupported folder scope '{scope}' (allowed: {', '.join(_VALID_SCOPES)})"
            )

    @staticmethod
    def _validate_name(name: str) -> str:
        if not isinstance(name, str):
            raise ValidationError("folder name must be a string")
        if name != name.strip():
            raise ValidationError("folder name must not have leading or trailing whitespace")
        clean = name.strip()
        if not clean:
            raise ValidationError("folder name is required")
        if len(clean) > _NAME_MAX:
            raise ValidationError(f"folder name must be {_NAME_MAX} characters or fewer")
        return clean

    def _get_folder_or_raise(self, folder_id: int, *, scope: FolderScope) -> dict[str, Any]:
        folder = self.repo.get_folder(folder_id)
        if folder["scope"] != scope:
            raise ValidationError(
                f"parent folder #{folder_id} belongs to scope '{folder['scope']}', not '{scope}'"
            )
        return folder