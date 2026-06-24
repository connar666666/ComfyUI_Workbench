from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn

from .api import create_app
from .config import load_settings


def _make_worker():
    """Build a WorkbenchWorker from current settings."""
    settings = load_settings()
    from .repositories import WorkbenchRepository
    from .storage import LocalStorage
    from .comfyui_adapter import WorkbenchComfyUIAdapter

    repo = WorkbenchRepository(settings.db_path)
    storage = LocalStorage(settings.root_dir)
    adapter = WorkbenchComfyUIAdapter(comfyui_url=settings.comfyui_url)

    from .worker import WorkbenchWorker
    return WorkbenchWorker(repo=repo, storage=storage, adapter=adapter)


@asynccontextmanager
async def lifespan(app):
    """Start background worker on app startup, stop on shutdown."""
    worker = _make_worker()
    stop_event = asyncio.Event()

    async def worker_loop():
        while not stop_event.is_set():
            try:
                await worker.run_once()
            except Exception:
                pass
            # Sleep a bit between polls; shorter if there might be more work
            await asyncio.sleep(2)

    task = asyncio.create_task(worker_loop())

    yield

    stop_event.set()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = create_app()
app.router.lifespan_context = lifespan


def main() -> None:
    uvicorn.run("workbench.main:app", host="0.0.0.0", port=8090, reload=True)


if __name__ == "__main__":
    main()
