from __future__ import annotations

from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .auth import CurrentUser, current_user_from_headers
from .config import WorkbenchSettings, load_settings
from .db import initialize_db
from .errors import WorkbenchError
from .repositories import WorkbenchRepository
from .services.assets import AssetService
from .services.jobs import JobService
from .storage import LocalStorage


class CreateJobRequest(BaseModel):
    prompt: str
    duration_sec: int
    resolution: str = "720x1280"
    audio_start_sec: float = 0
    reference_image_asset_id: int | None = None
    reference_audio_asset_id: int | None = None
    replace_audio_asset_id: int | None = None


def create_app(settings: WorkbenchSettings | None = None) -> FastAPI:
    settings = settings or load_settings()
    initialize_db(settings.db_path, settings.default_user, settings.default_role)
    storage = LocalStorage(settings.root_dir)
    storage.ensure_layout()
    repo = WorkbenchRepository(settings.db_path)

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

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/assets")
    def list_assets(kind: str | None = None):
        return AssetService(repo, storage).list_assets(kind=kind)

    @app.post("/api/assets")
    async def upload_asset(
        kind: str = Form(...),
        folder_id: int | None = Form(default=None),
        file: UploadFile = File(...),
        user: CurrentUser = Depends(current_user_from_headers),
    ):
        return AssetService(repo, storage).upload_asset(
            user=user,
            kind=kind,  # type: ignore[arg-type]
            filename=file.filename or "upload.bin",
            mime_type=file.content_type or "application/octet-stream",
            stream=file.file,
            folder_id=folder_id,
        )

    @app.get("/files/assets/{asset_id}")
    def stream_asset(asset_id: int):
        asset = repo.get_asset(asset_id)
        return FileResponse(storage.resolve(asset["storage_key"]), media_type=asset["mime_type"], filename=asset["original_filename"])

    @app.get("/api/jobs")
    def list_jobs():
        return JobService(repo).list_jobs()

    @app.post("/api/jobs")
    def create_job(payload: CreateJobRequest, user: CurrentUser = Depends(current_user_from_headers)):
        return JobService(repo).create_job(user=user, **payload.model_dump())

    return app
