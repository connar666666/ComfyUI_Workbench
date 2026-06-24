from __future__ import annotations

from dataclasses import dataclass

from comfyui.backend import ComfyUIBackend


@dataclass(frozen=True)
class SubmittedComfyJob:
    prompt_id: str
    raw_submission: object


@dataclass(frozen=True)
class CompletedComfyJob:
    prompt_id: str
    video_url: str
    local_path: str


class WorkbenchComfyUIAdapter:
    def __init__(self, *, backend: ComfyUIBackend | None = None, comfyui_url: str | None = None):
        if backend is not None:
            self.backend = backend
        elif comfyui_url is not None:
            self.backend = ComfyUIBackend(comfyui_url=comfyui_url)
        else:
            self.backend = ComfyUIBackend()

    async def submit(
        self,
        *,
        prompt: str,
        duration_sec: int,
        reference_image_path: str | None,
        reference_audio_path: str | None,
        replace_audio_path: str | None,
        audio_start_sec: float,
    ) -> SubmittedComfyJob:
        submission = await self.backend.submit_generation_request(
            prompt=prompt,
            duration=duration_sec,
            reference_image_url=reference_image_path,
            reference_audio_url=reference_audio_path,
            replace_audio_url=replace_audio_path,
            audio_start_sec=audio_start_sec,
        )
        return SubmittedComfyJob(prompt_id=submission.prompt_id, raw_submission=submission)

    async def await_result(self, submitted: SubmittedComfyJob) -> CompletedComfyJob:
        result = await self.backend.await_generation_result(submitted.raw_submission)
        if result.status != "done":
            raise RuntimeError(result.error or "ComfyUI generation failed")
        return CompletedComfyJob(
            prompt_id=result.task_id,
            video_url=result.video_url,
            local_path=result.video_url if result.video_url.startswith("/") else "",
        )
