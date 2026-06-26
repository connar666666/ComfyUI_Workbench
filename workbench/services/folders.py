from __future__ import annotations

from typing import Any, Literal

import psycopg

from ..auth import CurrentUser
from ..errors import ConflictError, ValidationError
from ..permissions import require_project_role
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
        user: CurrentUser,
        scope: FolderScope = "assets",
        parent_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        self._validate_scope(scope)
        if project_id is not None:
            require_project_role(self.repo, user, project_id, {"owner", "editor", "viewer"})
        return self.repo.list_folders(scope=scope, parent_id=parent_id, project_id=project_id)

    def create_folder(
        self,
        *,
        user: CurrentUser,
        scope: FolderScope = "assets",
        name: str,
        parent_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_scope(scope)
        clean_name = self._validate_name(name)
        if project_id is not None:
            require_project_role(self.repo, user, project_id, {"owner", "editor"})
        if parent_id is not None:
            parent = self._get_folder_or_raise(parent_id, scope=scope)
            if parent["project_id"] != project_id:
                raise ValidationError("parent folder belongs to a different project")
        if self.repo.find_folder_by_name(
            scope=scope, name=clean_name, parent_id=parent_id, project_id=project_id,
        ) is not None:
            raise ConflictError(
                f"a folder named '{clean_name}' already exists in this location"
            )
        try:
            actor_id = self.repo.resolve_user_id(user.id, user.username)
            folder_id = self.repo.create_folder(
                scope=scope,
                name=clean_name,
                parent_id=parent_id,
                project_id=project_id,
                created_by=actor_id,
            )
        except psycopg.IntegrityError as exc:
            raise ConflictError(
                f"a folder named '{clean_name}' already exists in this location"
            ) from exc
        return self.repo.get_folder(folder_id)

    def rename_folder(self, *, user: CurrentUser, folder_id: int, name: str) -> dict[str, Any]:
        clean_name = self._validate_name(name)
        existing = self.repo.get_folder(folder_id)
        if existing["project_id"] is not None:
            require_project_role(self.repo, user, existing["project_id"], {"owner", "editor"})
        if existing["scope"] != "assets":
            raise ValidationError("folder rename is only supported for assets scope")
        if self.repo.find_folder_by_name(
            scope=existing["scope"],
            name=clean_name,
            parent_id=existing["parent_id"],
            project_id=existing["project_id"],
            exclude_id=folder_id,
        ) is not None:
            raise ConflictError(
                f"a folder named '{clean_name}' already exists in this location"
            )
        try:
            self.repo.rename_folder(folder_id, clean_name)
        except psycopg.IntegrityError as exc:
            raise ConflictError(
                f"a folder named '{clean_name}' already exists in this location"
            ) from exc
        return self.repo.get_folder(folder_id)

    def delete_folder(self, *, user: CurrentUser, folder_id: int) -> None:
        folder = self.repo.get_folder(folder_id)
        if folder["project_id"] is not None:
            require_project_role(self.repo, user, folder["project_id"], {"owner", "editor"})
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
