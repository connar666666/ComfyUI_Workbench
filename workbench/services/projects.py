from __future__ import annotations

from ..auth import CurrentUser
from ..errors import ValidationError
from ..permissions import get_project_role, require_project_role
from ..repositories import WorkbenchRepository


class ProjectService:
    def __init__(self, repo: WorkbenchRepository):
        self.repo = repo

    def create_project(
        self,
        *,
        user: CurrentUser,
        name: str,
        description: str = "",
        members: list[dict] | None = None,
    ) -> dict:
        name = name.strip()
        if not name:
            raise ValidationError("project name is required")
        actor_id = self.repo.resolve_user_id(user.id, user.username)
        project = self.repo.create_project(name=name, description=description.strip(), created_by=actor_id)
        for member in members or []:
            user_id = str(member["user_id"])
            role = str(member["role"])
            self._validate_role(role)
            if user_id != actor_id:
                self.repo.set_project_member(project_id=project["id"], user_id=user_id, role=role)
        return self.get_project(user=user, project_id=project["id"])

    def list_projects(self, *, user: CurrentUser) -> list[dict]:
        return self.repo.list_projects(user_id=user.id, role=user.role)

    def get_project(self, *, user: CurrentUser, project_id: int) -> dict:
        role = get_project_role(self.repo, user, project_id)
        project = self.repo.get_project(project_id)
        project["current_user_role"] = role
        project["members"] = self.repo.list_project_members(project_id)
        return project

    def set_member(self, *, user: CurrentUser, project_id: int, member_user_id: int, role: str) -> dict:
        require_project_role(self.repo, user, project_id, {"owner"})
        self._validate_role(role)
        return self.repo.set_project_member(project_id=project_id, user_id=member_user_id, role=role)

    def remove_member(self, *, user: CurrentUser, project_id: int, member_user_id: int) -> None:
        require_project_role(self.repo, user, project_id, {"owner"})
        self.repo.remove_project_member(project_id=project_id, user_id=member_user_id)

    @staticmethod
    def _validate_role(role: str) -> None:
        if role not in {"owner", "editor", "viewer"}:
            raise ValidationError("unsupported project role")
