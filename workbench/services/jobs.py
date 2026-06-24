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
    ) -> dict:
        prompt = prompt.strip()
        if not prompt:
            raise ValidationError("prompt is required")
        if duration_sec < 1 or duration_sec > 60:
            raise ValidationError("duration_sec must be between 1 and 60")
        if resolution not in ("720x1280", "1280x720", "1024x1024"):
            raise ValidationError("unsupported resolution")
        return self.repo.create_job(
            created_by=user.id,
            prompt=prompt,
            duration_sec=duration_sec,
            resolution=resolution,
            audio_start_sec=audio_start_sec,
            reference_image_asset_id=reference_image_asset_id,
            reference_audio_asset_id=reference_audio_asset_id,
            replace_audio_asset_id=replace_audio_asset_id,
        )

    def list_jobs(self) -> list[dict]:
        return self.repo.list_jobs()
