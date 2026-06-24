from __future__ import annotations

from .auth import CurrentUser
from .errors import PermissionDeniedError


def require_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise PermissionDeniedError("admin role required")


def require_owner_or_admin(user: CurrentUser, owner_id: int | None) -> None:
    if user.role == "admin":
        return
    if owner_id is not None and user.id == owner_id:
        return
    raise PermissionDeniedError("owner or admin required")
