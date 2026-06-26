from __future__ import annotations

from io import BytesIO
from typing import Any

from ..auth import CurrentUser
from ..errors import ValidationError
from ..models import AssetKind
from ..permissions import require_project_role
from ..remote_workflows import RemoteWorkflowClient
from ..repositories import WorkbenchRepository
from ..storage import LocalStorage


RESULT_KIND_BY_TYPE: dict[str, AssetKind] = {
    "image": "image",
    "audio": "audio",
    "video": "video",
    "document": "document",
}


class ProjectWorkflowService:
    def __init__(
        self,
        repo: WorkbenchRepository,
        remote_client: RemoteWorkflowClient,
        storage: LocalStorage | None = None,
    ):
        self.repo = repo
        self.remote_client = remote_client
        self.storage = storage

    def list_workflows(self, *, user: CurrentUser, project_id: int) -> list[dict]:
        require_project_role(self.repo, user, project_id, {"owner", "editor", "viewer"})
        return self.repo.list_project_workflows(project_id)

    def add_workflow(
        self,
        *,
        user: CurrentUser,
        project_id: int,
        workflow_id: str,
        display_name: str | None,
        defaults: dict[str, Any] | None,
    ) -> dict:
        require_project_role(self.repo, user, project_id, {"owner"})
        workflow_id = workflow_id.strip()
        if not workflow_id:
            raise ValidationError("workflow_id is required")
        return self.repo.create_project_workflow(
            project_id=project_id,
            workflow_id=workflow_id,
            display_name=display_name.strip() if display_name else None,
            defaults=defaults or {},
            created_by=user.id,
        )

    def run_workflow(
        self,
        *,
        user: CurrentUser,
        project_id: int,
        project_workflow_id: int,
        input_values: dict[str, Any],
    ) -> dict:
        require_project_role(self.repo, user, project_id, {"owner", "editor"})
        workflow = self.repo.get_project_workflow(project_workflow_id)
        if workflow["project_id"] != project_id:
            raise ValidationError("workflow is not selected for this project")
        if not workflow["enabled"]:
            raise ValidationError("workflow is disabled")

        run = self.repo.create_remote_workflow_run(
            project_id=project_id,
            project_workflow_id=project_workflow_id,
            workflow_id=workflow["workflow_id"],
            input_values=input_values,
            created_by=user.id,
        )
        try:
            remote_run = self.remote_client.run_workflow(workflow["workflow_id"], input_values)
        except Exception as exc:
            return self.repo.update_remote_workflow_run_result(
                run_id=run["id"],
                status="failed",
                results=[],
                error_message=str(exc),
            )
        return self.repo.mark_remote_workflow_run_started(run["id"], remote_run["prompt_id"])

    def refresh_run(self, *, user: CurrentUser, project_id: int, run_id: int) -> dict:
        require_project_role(self.repo, user, project_id, {"owner", "editor", "viewer"})
        run = self.repo.get_remote_workflow_run(run_id)
        if run["project_id"] != project_id:
            raise ValidationError("run does not belong to this project")
        if not run.get("prompt_id"):
            return run

        result = self.remote_client.get_result(run["prompt_id"])
        status = "running" if result.get("pending") else "succeeded"
        results = result.get("results", [])
        saved_asset_ids = run.get("saved_asset_ids", [])
        if status == "succeeded":
            saved_asset_ids = self._save_results(
                project_id=project_id,
                results=results,
                created_by=user.id,
                existing_asset_ids=saved_asset_ids,
            )
        return self.repo.update_remote_workflow_run_result(
            run_id=run_id,
            status=status,
            results=results,
            saved_asset_ids=saved_asset_ids,
        )

    def _save_results(
        self,
        *,
        project_id: int,
        results: list[dict[str, Any]],
        created_by: int,
        existing_asset_ids: list[int],
    ) -> list[int]:
        if self.storage is None:
            return existing_asset_ids
        saved_asset_ids = list(existing_asset_ids)
        if saved_asset_ids:
            return saved_asset_ids
        for index, item in enumerate(results):
            url = item.get("download_url") or item.get("url")
            if not isinstance(url, str) or not url:
                continue
            kind = RESULT_KIND_BY_TYPE.get(str(item.get("type")), "document")
            filename = str(item.get("filename") or f"remote-result-{index + 1}")
            try:
                content, content_type = self.remote_client.download_file(url)
                stored = self.storage.store_asset(kind, filename, BytesIO(content))
            except Exception:
                continue
            asset = self.repo.create_asset(
                project_id=project_id,
                kind=kind,
                original_filename=filename,
                storage_key=stored.storage_key,
                mime_type=content_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
                uploaded_by=created_by,
                folder_id=None,
            )
            saved_asset_ids.append(asset["id"])
        return saved_asset_ids
