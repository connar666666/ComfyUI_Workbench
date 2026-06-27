from __future__ import annotations

import httpx
import hashlib
from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from .auth import CurrentUser, get_current_user
from .config import WorkbenchSettings, load_settings
from .db import database_url_for_schema, initialize_db
from .errors import PermissionDeniedError, ServiceUnavailableError, ValidationError, WorkbenchError
from .repositories import WorkbenchRepository
from .permissions import require_project_role
from .services.assets import AssetService
from .services.folders import FolderService
from .services.jobs import JobService
from .services.projects import ProjectService
from .services.project_workflows import ProjectWorkflowService
from .sse import EventType, get_event_bus


class CreateJobRequest(BaseModel):
    prompt: str
    duration_sec: int
    resolution: str = "720x1280"
    audio_start_sec: float = 0
    reference_image_asset_id: str | None = None
    reference_audio_asset_id: str | None = None
    replace_audio_asset_id: str | None = None
    canvas_id: str | None = None
    canvas_node_id: str | None = None
    canvas_version_id: str | None = None


class LiveblocksAuthRequest(BaseModel):
    room: str


class ResolveUsersRequest(BaseModel):
    userIds: list[str]


class RunRemoteWorkflowRequest(BaseModel):
    input_values: dict[str, object]


class ProjectMemberInput(BaseModel):
    user_id: str
    role: str


class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    members: list[ProjectMemberInput] = []


class SetProjectMemberRequest(BaseModel):
    role: str


class AddProjectWorkflowRequest(BaseModel):
    workflow_id: str
    display_name: str | None = None
    defaults: dict[str, object] = {}


class CreateFolderRequest(BaseModel):
    scope: str = "assets"
    name: str
    description: str = ""
    parent_id: str | None = None
    project_id: str | None = None


class RenameFolderRequest(BaseModel):
    name: str


def _user_color(user_id: str) -> str:
    if user_id.isdigit():
        return f"hsl({(int(user_id) * 47) % 360} 70% 45%)"
    return "hsl(210 70% 45%)"


def create_app(settings: WorkbenchSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    database_url = settings.database_url
    test_schema = None
    if settings.storage_backend == "local" and str(settings.db_path).endswith(".sqlite"):
        digest = hashlib.sha1(str(settings.db_path).encode("utf-8")).hexdigest()[:16]
        test_schema = f"workbench_{digest}"
        database_url = database_url_for_schema(settings.database_url, test_schema)
    initialize_db(settings.database_url, settings.default_user, settings.default_role, schema=test_schema)
    storage = build_storage(settings)
    storage.ensure_layout()
    repo = WorkbenchRepository(database_url)
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
        folder_id: str | None = None,
        user: CurrentUser = Depends(get_current_user),
    ):
        return AssetService(repo, storage).list_assets(
            kind=kind, user_id=user.id, role=user.role, folder_id=folder_id,
        )

    # ── Folders ─────────────────────────────────────────────────────

    @app.get("/api/folders")
    def list_folders(
        scope: str = "assets",
        parent_id: str | None = None,
        project_id: str | None = None,
        user: CurrentUser = Depends(get_current_user),
    ):
        return FolderService(repo).list_folders(
            user=user, scope=scope, parent_id=parent_id, project_id=project_id,
        )

    @app.post("/api/folders")
    def create_folder(
        payload: CreateFolderRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        return FolderService(repo).create_folder(
            user=user,
            scope=payload.scope,
            name=payload.name,
            description=payload.description,
            parent_id=payload.parent_id,
            project_id=payload.project_id,
        )

    @app.patch("/api/folders/{folder_id}")
    def rename_folder(
        folder_id: str,
        payload: RenameFolderRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        return FolderService(repo).rename_folder(
            user=user, folder_id=folder_id, name=payload.name,
        )

    @app.delete("/api/folders/{folder_id}")
    def delete_folder(
        folder_id: str,
        user: CurrentUser = Depends(get_current_user),
    ):
        FolderService(repo).delete_folder(user=user, folder_id=folder_id)
        return {"ok": True}

    # ── Projects ─────────────────────────────────────────────────────

    @app.get("/api/projects")
    def list_projects(user: CurrentUser = Depends(get_current_user)):
        return ProjectService(repo).list_projects(user=user)

    @app.post("/api/projects")
    def create_project(
        payload: CreateProjectRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        return ProjectService(repo).create_project(
            user=user,
            name=payload.name,
            description=payload.description,
            members=[item.model_dump() for item in payload.members],
        )

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str, user: CurrentUser = Depends(get_current_user)):
        return ProjectService(repo).get_project(user=user, project_id=project_id)

    @app.put("/api/projects/{project_id}/members/{member_user_id}")
    def set_project_member(
        project_id: str,
        member_user_id: str,
        payload: SetProjectMemberRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        return ProjectService(repo).set_member(
            user=user,
            project_id=project_id,
            member_user_id=member_user_id,
            role=payload.role,
        )

    @app.delete("/api/projects/{project_id}/members/{member_user_id}")
    def remove_project_member(
        project_id: str,
        member_user_id: str,
        user: CurrentUser = Depends(get_current_user),
    ):
        ProjectService(repo).remove_member(user=user, project_id=project_id, member_user_id=member_user_id)
        return {"ok": True}

    @app.get("/api/projects/{project_id}/assets")
    def list_project_assets(
        project_id: str,
        kind: str | None = None,
        folder_id: str | None = None,
        user: CurrentUser = Depends(get_current_user),
    ):
        require_project_role(repo, user, project_id, {"owner", "editor", "viewer"})
        return AssetService(repo, storage).list_assets(
            kind=kind, project_id=project_id, role="admin", folder_id=folder_id,
        )

    @app.post("/api/projects/{project_id}/assets")
    async def upload_project_asset(
        project_id: str,
        kind: str = Form(...),
        folder_id: str | None = Form(default=None),
        file: UploadFile = File(...),
        user: CurrentUser = Depends(get_current_user),
    ):
        require_project_role(repo, user, project_id, {"owner", "editor"})
        result = AssetService(repo, storage).upload_asset(
            user=user,
            kind=kind,  # type: ignore[arg-type]
            filename=file.filename or "upload.bin",
            mime_type=file.content_type or "application/octet-stream",
            stream=file.file,
            folder_id=folder_id,
            project_id=project_id,
        )
        event_bus.publish(EventType.ASSET_UPLOADED, {"asset": result}, visible_to="all")
        return result

    @app.get("/api/projects/{project_id}/workflows")
    def list_project_workflows(project_id: str, user: CurrentUser = Depends(get_current_user)):
        from .remote_workflows import RemoteWorkflowClient

        service = ProjectWorkflowService(repo, RemoteWorkflowClient(settings.zealman_base_url, settings.zealman_token), storage)
        return service.list_workflows(user=user, project_id=project_id)

    @app.post("/api/projects/{project_id}/workflows")
    def add_project_workflow(
        project_id: str,
        payload: AddProjectWorkflowRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        from .remote_workflows import RemoteWorkflowClient

        service = ProjectWorkflowService(repo, RemoteWorkflowClient(settings.zealman_base_url, settings.zealman_token), storage)
        return service.add_workflow(
            user=user,
            project_id=project_id,
            workflow_id=payload.workflow_id,
            display_name=payload.display_name,
            defaults=payload.defaults,
        )

    @app.post("/api/projects/{project_id}/workflows/{project_workflow_id}/runs")
    def run_project_workflow(
        project_id: str,
        project_workflow_id: str,
        payload: RunRemoteWorkflowRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        from .remote_workflows import RemoteWorkflowClient

        service = ProjectWorkflowService(repo, RemoteWorkflowClient(settings.zealman_base_url, settings.zealman_token), storage)
        return service.run_workflow(
            user=user,
            project_id=project_id,
            project_workflow_id=project_workflow_id,
            input_values=payload.input_values,
        )

    @app.post("/api/projects/{project_id}/remote-runs/{run_id}/refresh")
    def refresh_project_remote_run(
        project_id: str,
        run_id: str,
        user: CurrentUser = Depends(get_current_user),
    ):
        from .remote_workflows import RemoteWorkflowClient

        service = ProjectWorkflowService(repo, RemoteWorkflowClient(settings.zealman_base_url, settings.zealman_token), storage)
        return service.refresh_run(user=user, project_id=project_id, run_id=run_id)

    @app.get("/api/projects/{project_id}/history")
    def list_project_history(project_id: str, user: CurrentUser = Depends(get_current_user)):
        require_project_role(repo, user, project_id, {"owner", "editor", "viewer"})
        return repo.list_project_history(project_id)

    @app.post("/api/assets")
    async def upload_asset(
        kind: str = Form(...),
        folder_id: str | None = Form(default=None),
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
    def stream_asset(asset_id: str):
        asset = repo.get_asset(asset_id)
        if hasattr(storage, "open"):
            return StreamingResponse(storage.open(asset["storage_key"]), media_type=asset["mime_type"])
        return FileResponse(storage.resolve(asset["storage_key"]), media_type=asset["mime_type"], filename=asset["original_filename"])

    @app.delete("/api/assets/{asset_id}")
    def delete_asset(asset_id: str, user: CurrentUser = Depends(get_current_user)):
        asset = repo.get_asset(asset_id)
        if asset.get("project_id"):
            require_project_role(repo, user, asset["project_id"], {"owner", "editor"})
        elif user.role != "admin" and asset.get("uploaded_by") != user.id:
            raise PermissionDeniedError("you can only delete assets you uploaded")
        repo.delete_asset(asset_id)
        return {"ok": True}

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
    def cancel_job(job_id: str, user: CurrentUser = Depends(get_current_user)):
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
    def stream_video(video_id: str):
        video = repo.get_video(video_id)
        if hasattr(storage, "open"):
            return StreamingResponse(storage.open(video["storage_key"]), media_type=video["mime_type"])
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

    # ── Remote Workflows ─────────────────────────────────────────────

    @app.get("/api/remote-workflows")
    def list_remote_workflows(user: CurrentUser = Depends(get_current_user)):
        from .remote_workflows import RemoteWorkflowClient

        client = RemoteWorkflowClient(settings.zealman_base_url, settings.zealman_token)
        return {"workflows": client.list_workflows()}

    @app.post("/api/remote-workflows/uploads")
    async def upload_remote_workflow_file(
        file: UploadFile = File(...),
        overwrite: bool = Form(default=False),
        user: CurrentUser = Depends(get_current_user),
    ):
        from .remote_workflows import RemoteWorkflowClient

        client = RemoteWorkflowClient(settings.zealman_base_url, settings.zealman_token)
        return client.upload_file(
            file=file.file,
            filename=file.filename or "upload.bin",
            content_type=file.content_type,
            overwrite=overwrite,
        )

    @app.get("/api/remote-workflows/runs/{prompt_id}")
    def get_remote_workflow_result(
        prompt_id: str,
        user: CurrentUser = Depends(get_current_user),
    ):
        from .remote_workflows import RemoteWorkflowClient

        client = RemoteWorkflowClient(settings.zealman_base_url, settings.zealman_token)
        return client.get_result(prompt_id)

    @app.get("/api/remote-workflows/{workflow_id}")
    def get_remote_workflow(
        workflow_id: str,
        user: CurrentUser = Depends(get_current_user),
    ):
        from .remote_workflows import RemoteWorkflowClient

        client = RemoteWorkflowClient(settings.zealman_base_url, settings.zealman_token)
        return client.get_workflow(workflow_id)

    @app.post("/api/remote-workflows/{workflow_id}/run")
    def run_remote_workflow(
        workflow_id: str,
        payload: RunRemoteWorkflowRequest,
        user: CurrentUser = Depends(get_current_user),
    ):
        from .remote_workflows import RemoteWorkflowClient

        client = RemoteWorkflowClient(settings.zealman_base_url, settings.zealman_token)
        return client.run_workflow(workflow_id, payload.input_values)

    # ── Users ────────────────────────────────────────────────────────

    @app.get("/api/users")
    def list_users(user: CurrentUser = Depends(get_current_user)):
        return repo.list_users()

    return app


# Lazy import to avoid circular dependency
from .storage import build_storage
