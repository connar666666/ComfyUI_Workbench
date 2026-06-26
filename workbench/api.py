from __future__ import annotations

import httpx
from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .auth import CurrentUser, get_current_user
from .config import WorkbenchSettings, load_settings
from .db import initialize_db
from .errors import PermissionDeniedError, ServiceUnavailableError, ValidationError, WorkbenchError
from .repositories import WorkbenchRepository
from .services.assets import AssetService
from .services.jobs import JobService
from .sse import EventType, get_event_bus


class CreateJobRequest(BaseModel):
    prompt: str
    duration_sec: int
    resolution: str = "720x1280"
    audio_start_sec: float = 0
    reference_image_asset_id: int | None = None
    reference_audio_asset_id: int | None = None
    replace_audio_asset_id: int | None = None
    canvas_id: str | None = None
    canvas_node_id: str | None = None
    canvas_version_id: int | None = None


class LiveblocksAuthRequest(BaseModel):
    room: str


class ResolveUsersRequest(BaseModel):
    userIds: list[str]


def _user_color(user_id: str) -> str:
    if user_id.isdigit():
        return f"hsl({(int(user_id) * 47) % 360} 70% 45%)"
    return "hsl(210 70% 45%)"


def create_app(settings: WorkbenchSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    initialize_db(settings.db_path, settings.default_user, settings.default_role)
    storage = LocalStorage(settings.root_dir)
    storage.ensure_layout()
    repo = WorkbenchRepository(settings.db_path)
    event_bus = get_event_bus()

    app = FastAPI(title="ComfyUI Workbench")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(WorkbenchError)
    async def handle_workbench_error(_request, exc: WorkbenchError):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": str(exc)})

    # ── Auth routes ──────────────────────────────────────────────────

    from .routes_auth import router as auth_router
    app.include_router(auth_router)

    # ── SSE endpoint ─────────────────────────────────────────────────

    from .sse import sse_endpoint
    app.add_api_route("/api/events", sse_endpoint, methods=["GET"], tags=["events"])

    # ── Health ───────────────────────────────────────────────────────

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    # ── Liveblocks ───────────────────────────────────────────────────

    @app.post("/api/liveblocks-auth")
    def liveblocks_auth(
        payload: LiveblocksAuthRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        if not payload.room.startswith("canvas:"):
            raise PermissionDeniedError("invalid Liveblocks room")
        if not settings.liveblocks_secret_key:
            raise ValidationError("LIVEBLOCKS_SECRET_KEY is not configured")

        user_record = repo.get_user_by_id(user.id)
        body = {
            "userId": str(user.id),
            "userInfo": {
                "name": user_record.get("display_name") or user.username,
                "avatar": None,
                "color": _user_color(str(user.id)),
            },
            "permissions": {
                payload.room: ["room:write"],
            },
        }
        try:
            response = httpx.post(
                "https://api.liveblocks.io/v2/authorize-user",
                headers={
                    "Authorization": f"Bearer {settings.liveblocks_secret_key}",
                    "Content-Type": "application/json",
                },
                json=body,
                timeout=10,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code in {401, 403}:
                raise ValidationError("Liveblocks authentication failed. Check LIVEBLOCKS_SECRET_KEY.") from exc
            raise ValidationError("Liveblocks authorization failed") from exc
        except httpx.HTTPError as exc:
            raise ValidationError("Liveblocks collaboration service is unreachable") from exc
        return response.json()

    @app.post("/api/liveblocks/resolve-users")
    def resolve_liveblocks_users(
        payload: ResolveUsersRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        users = repo.list_users()
        by_id = {str(item["id"]): item for item in users}
        return [
            {
                "id": user_id,
                "name": by_id.get(user_id, {}).get("display_name")
                or by_id.get(user_id, {}).get("username")
                or f"user#{user_id}",
                "color": _user_color(user_id),
            }
            for user_id in payload.userIds
        ]

    # ── Assets ───────────────────────────────────────────────────────

    @app.get("/api/assets")
    def list_assets(
        kind: str | None = None,
        user: CurrentUser = Depends(get_current_user),
    ):
        return AssetService(repo, storage).list_assets(
            kind=kind, user_id=user.id, role=user.role,
        )

    @app.post("/api/assets")
    async def upload_asset(
        kind: str = Form(...),
        folder_id: int | None = Form(default=None),
        file: UploadFile = File(...),
        user: CurrentUser = Depends(get_current_user),
    ):
        result = AssetService(repo, storage).upload_asset(
            user=user,
            kind=kind,  # type: ignore[arg-type]
            filename=file.filename or "upload.bin",
            mime_type=file.content_type or "application/octet-stream",
            stream=file.file,
            folder_id=folder_id,
        )
        event_bus.publish(EventType.ASSET_UPLOADED, {"asset": result}, visible_to="all")
        return result

    @app.get("/files/assets/{asset_id}")
    def stream_asset(asset_id: int):
        asset = repo.get_asset(asset_id)
        return FileResponse(storage.resolve(asset["storage_key"]), media_type=asset["mime_type"], filename=asset["original_filename"])

    # ── Jobs ─────────────────────────────────────────────────────────

    @app.get("/api/jobs")
    def list_jobs(user: CurrentUser = Depends(get_current_user)):
        return JobService(repo).list_jobs(user_id=user.id, role=user.role)

    @app.post("/api/jobs")
    def create_job(
        payload: CreateJobRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        job = JobService(repo).create_job(user=user, **payload.model_dump())
        event_bus.publish(EventType.JOB_CREATED, {"job": job}, visible_to="all")
        return job

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: int, user: CurrentUser = Depends(get_current_user)):
        repo.cancel_job(job_id, user_id=user.id, role=user.role)
        job = repo.get_job(job_id)
        event_bus.publish(EventType.JOB_STATUS_CHANGED, {"job": job}, visible_to="all")
        return job

    # ── Canvas Versions ──────────────────────────────────────────────

    @app.get("/api/canvas/{canvas_id}/versions")
    def list_canvas_versions(
        canvas_id: str,
        user: CurrentUser = Depends(get_current_user),
    ):
        return repo.list_node_versions(canvas_id)

    @app.get("/api/canvas/{canvas_id}/nodes/{node_id}/versions")
    def list_canvas_node_versions(
        canvas_id: str,
        node_id: str,
        user: CurrentUser = Depends(get_current_user),
    ):
        return repo.list_node_versions(canvas_id, node_id)

    # ── Videos ───────────────────────────────────────────────────────

    @app.get("/api/videos")
    def list_videos():
        return repo.list_videos()

    @app.get("/files/videos/{video_id}")
    def stream_video(video_id: int):
        video = repo.get_video(video_id)
        return FileResponse(
            storage.resolve(video["storage_key"]),
            media_type=video["mime_type"],
            filename=video["title"],
        )

    # ── ComfyUI Queue ────────────────────────────────────────────────

    @app.get("/api/comfyui/queue")
    def comfyui_queue():
        from .comfyui_queue import ComfyUIQueueClient
        client = ComfyUIQueueClient(settings.comfyui_url)
        try:
            return client.fetch_queue()
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError("ComfyUI queue is unavailable") from exc
        except ValueError as exc:
            raise ServiceUnavailableError("ComfyUI queue returned an invalid response") from exc

    # ── Users ────────────────────────────────────────────────────────

    @app.get("/api/users")
    def list_users(user: CurrentUser = Depends(get_current_user)):
        return repo.list_users()

    return app


# Lazy import to avoid circular dependency
from .storage import LocalStorage
