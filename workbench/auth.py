from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header

from .models import UserRole


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    role: UserRole


def current_user_from_headers(
    x_workbench_user: str | None = Header(default=None),
    x_workbench_user_id: str | None = Header(default=None),
    x_workbench_role: str | None = Header(default=None),
) -> CurrentUser:
    username = x_workbench_user or "local-user"
    user_id = int(x_workbench_user_id or "1")
    role = x_workbench_role if x_workbench_role in ("member", "admin") else "admin"
    return CurrentUser(id=user_id, username=username, role=role)  # type: ignore[arg-type]
