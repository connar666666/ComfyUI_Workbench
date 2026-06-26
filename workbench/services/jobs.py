from __future__ import annotations

from ..auth import CurrentUser
from ..errors import ValidationError
from ..repositories import WorkbenchRepository


class JobService:
    def __init__(self, repo: WorkbenchRepository):
        self.repo = repo

    def create_job(
        self,
        *,
        user: CurrentUser,
        prompt: str,
        duration_sec: int,
        resolution: str,
        audio_start_sec: float,
        reference_image_asset_id: int | None,
        reference_audio_asset_id: int | None,
        replace_audio_asset_id: int | None,
        canvas_id: str | None = None,
        canvas_node_id: str | None = None,
        canvas_version_id: int | None = None,
        project_id: int | None = None,
    ) -> dict:
        prompt = prompt.strip()
        if not prompt:
            raise ValidationError("prompt is required")
        if duration_sec < 1 or duration_sec > 60:
            raise ValidationError("duration_sec must be between 1 and 60")
        if resolution not in ("720x1280", "1280x720", "1024x1024"):
            raise ValidationError("unsupported resolution")
        actor_id = self.repo.resolve_user_id(user.id, user.username)
        return self.repo.create_job(
            project_id=project_id,
            created_by=actor_id,
            prompt=prompt,
            duration_sec=duration_sec,
            resolution=resolution,
            audio_start_sec=audio_start_sec,
            reference_image_asset_id=reference_image_asset_id,
            reference_audio_asset_id=reference_audio_asset_id,
            replace_audio_asset_id=replace_audio_asset_id,
            canvas_id=canvas_id,
            canvas_node_id=canvas_node_id,
            canvas_version_id=canvas_version_id,
        )

    def list_jobs(
        self,
        user_id: int | None = None,
        role: str | None = None,
        project_id: int | None = None,
    ) -> list[dict]:
        return self.repo.list_jobs(user_id=user_id, role=role, project_id=project_id)
