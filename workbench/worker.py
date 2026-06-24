from __future__ import annotations

from pathlib import Path
from typing import Any

from .repositories import WorkbenchRepository


class WorkbenchWorker:
    def __init__(self, *, repo: WorkbenchRepository, storage_root: Path, adapter: Any):
        self.repo = repo
        self.storage_root = storage_root
        self.adapter = adapter

    async def run_once(self) -> dict | None:
        job = self.repo.claim_next_job()
        if job is None:
            return None
        try:
            submitted = await self.adapter.submit(
                prompt=job["prompt"],
                duration_sec=job["duration_sec"],
                reference_image_path=None,
                reference_audio_path=None,
                replace_audio_path=None,
                audio_start_sec=job["audio_start_sec"],
            )
            self.repo.record_comfyui_task(
                job_id=job["id"],
                prompt_id=submitted.prompt_id,
                comfyui_url="",
                native_status="running",
            )
            await self.adapter.await_result(submitted)
            self.repo.mark_job_succeeded(job["id"], output_video_id=None)
            return self.repo.get_job(job["id"])
        except Exception as exc:
            self.repo.mark_job_failed(job["id"], "internal_error", str(exc))
            return self.repo.get_job(job["id"])
