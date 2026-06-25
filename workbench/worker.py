from __future__ import annotations

from pathlib import Path

from .repositories import WorkbenchRepository
from .storage import LocalStorage
from .sse import EventBus, EventType, get_event_bus


class WorkbenchWorker:
    def __init__(
        self,
        *,
        repo: WorkbenchRepository,
        storage: LocalStorage,
        adapter,
    ):
        self.repo = repo
        self.storage = storage
        self.adapter = adapter
        self._event_bus: EventBus | None = None

    @property
    def event_bus(self) -> EventBus:
        if self._event_bus is None:
            self._event_bus = get_event_bus()
        return self._event_bus

    def _resolve_asset_path(self, asset_id: int | None) -> str | None:
        """Resolve an asset ID to a local file path."""
        if asset_id is None:
            return None
        try:
            asset = self.repo.get_asset(asset_id)
            return str(self.storage.resolve(asset["storage_key"]))
        except Exception:
            return None

    async def run_once(self) -> dict | None:
        job = self.repo.claim_next_job()
        if job is None:
            return None

        # Publish status change
        self.event_bus.publish(EventType.JOB_STATUS_CHANGED, {"job": job}, visible_to="all")

        try:
            # Resolve reference asset paths from DB records
            reference_image_path = self._resolve_asset_path(job.get("reference_image_asset_id"))
            reference_audio_path = self._resolve_asset_path(job.get("reference_audio_asset_id"))
            replace_audio_path = self._resolve_asset_path(job.get("replace_audio_asset_id"))

            submitted = await self.adapter.submit(
                prompt=job["prompt"],
                duration_sec=job["duration_sec"],
                reference_image_path=reference_image_path,
                reference_audio_path=reference_audio_path,
                replace_audio_path=replace_audio_path,
                audio_start_sec=job["audio_start_sec"],
            )
            self.repo.record_comfyui_task(
                job_id=job["id"],
                prompt_id=submitted.prompt_id,
                comfyui_url="",
                native_status="running",
            )

            self.event_bus.publish(
                EventType.JOB_PROGRESS,
                {"job_id": job["id"], "stage": "generating", "prompt_id": submitted.prompt_id},
                visible_to="all",
            )

            result = await self.adapter.await_result(submitted)

            # Archive the output video into our storage
            video_id = None
            if result.local_path:
                local = Path(result.local_path)
                if local.exists():
                    try:
                        stored = self.storage.archive_video(local, local.name)
                        video = self.repo.create_video(
                            source_job_id=job["id"],
                            created_by=job["created_by"],
                            title=job["prompt"][:80],
                            storage_key=stored.storage_key,
                            mime_type="video/mp4",
                            size_bytes=stored.size_bytes,
                            prompt=job["prompt"],
                        )
                        video_id = video["id"]
                    except Exception:
                        pass  # video archiving is best-effort

            self.repo.mark_job_succeeded(job["id"], output_video_id=video_id)
            final_job = self.repo.get_job(job["id"])
            if final_job.get("canvas_id") and final_job.get("canvas_node_id"):
                input_asset_ids = [
                    asset_id
                    for asset_id in [
                        final_job.get("reference_image_asset_id"),
                        final_job.get("reference_audio_asset_id"),
                        final_job.get("replace_audio_asset_id"),
                    ]
                    if asset_id is not None
                ]
                version = self.repo.create_node_version(
                    canvas_id=final_job["canvas_id"],
                    node_id=final_job["canvas_node_id"],
                    generation_job_id=final_job["id"],
                    output_video_id=final_job.get("output_video_id"),
                    prompt=final_job["prompt"],
                    input_asset_ids=input_asset_ids,
                    params={
                        "duration_sec": final_job["duration_sec"],
                        "resolution": final_job["resolution"],
                        "audio_start_sec": final_job["audio_start_sec"],
                    },
                    snapshot={"job": final_job},
                    status=final_job["status"],
                    created_by=final_job["created_by"],
                )
                self.repo.set_job_canvas_version(final_job["id"], version["id"])
                final_job = self.repo.get_job(job["id"])
            self.event_bus.publish(EventType.JOB_STATUS_CHANGED, {"job": final_job}, visible_to="all")
            return final_job

        except Exception as exc:
            self.repo.mark_job_failed(job["id"], "internal_error", str(exc))
            final_job = self.repo.get_job(job["id"])
            self.event_bus.publish(EventType.JOB_STATUS_CHANGED, {"job": final_job}, visible_to="all")
            return final_job
