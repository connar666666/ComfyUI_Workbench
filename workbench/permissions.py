from __future__ import annotations

from .auth import CurrentUser
from .errors import PermissionDeniedError
from .repositories import WorkbenchRepository


def require_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise PermissionDeniedError("admin role required")


def require_owner_or_admin(user: CurrentUser, owner_id: int | None) -> None:
    if user.role == "admin":
        return
    if owner_id is not None and user.id == owner_id:
        return
    raise PermissionDeniedError("owner or admin required")


def get_project_role(repo: WorkbenchRepository, user: CurrentUser, project_id: int) -> str:
    repo.get_project(project_id)
    if user.role == "admin":
        return "owner"
    member = repo.get_project_member(project_id, user.id)
    if member is None:
        raise PermissionDeniedError("project membership required")
    return member["role"]


def require_project_role(
    repo: WorkbenchRepository,
    user: CurrentUser,
    project_id: int,
    allowed_roles: set[str],
) -> str:
    role = get_project_role(repo, user, project_id)
    if role not in allowed_roles:
        raise PermissionDeniedError("project role does not allow this action")
    return role
