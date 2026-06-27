from __future__ import annotations

import hashlib
import tempfile
from io import BytesIO
from pathlib import Path

import pytest

from workbench.auth import CurrentUser
from workbench.config import WorkbenchSettings
from workbench.db import initialize_db
from workbench.errors import ConflictError, ValidationError
from workbench.remote_workflows import RemoteWorkflowClient
from workbench.repositories import WorkbenchRepository
from workbench.services.assets import AssetService
from workbench.services.folders import FolderService
from workbench.services.jobs import JobService
from workbench.services.project_workflows import ProjectWorkflowService
from workbench.services.projects import ProjectService
from workbench.storage import LocalStorage


def _bootstrap():
    """Return (repo, settings, storage, root_dir) for one isolated test schema."""
    tmp = tempfile.TemporaryDirectory()
    root_dir = Path(tmp.name) / "root"
    root_dir.mkdir()
    settings = WorkbenchSettings(
        root_dir=root_dir,
        db_path=root_dir / "workbench.sqlite",
        comfyui_url="http://127.0.0.1:8188",
        zealman_base_url=None,
        zealman_token=None,
        default_user="default-admin",
        default_role="admin",
        jwt_secret="test-secret",
        jwt_expiry_hours=24,
        invite_token_bytes=16,
        invite_expiry_days=7,
        liveblocks_secret_key=None,
    )
    import hashlib
    digest = hashlib.sha1(str(settings.db_path).encode()).hexdigest()[:16]
    schema = f"workbench_{digest}"
    initialize_db(settings.database_url, settings.default_user, settings.default_role, schema=schema)
    repo = WorkbenchRepository(settings.db_path)
    storage = LocalStorage(root_dir)
    storage.ensure_layout()
    return repo, storage, tmp


@pytest.fixture
def ctx():
    repo, storage, tmp = _bootstrap()
    yield repo, storage
    tmp.cleanup()


@pytest.fixture
def admin_user(ctx) -> CurrentUser:
    repo, _storage = ctx
    user = repo.get_user_by_username("default-admin")
    return CurrentUser(id=str(user["id"]), username="owner", role="admin")


class TestFolderService:
    def test_create_folder_rejects_blank_name(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = FolderService(repo)
        with pytest.raises(ValidationError):
            service.create_folder(user=admin_user, name="")

    def test_create_folder_rejects_long_name(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = FolderService(repo)
        with pytest.raises(ValidationError):
            service.create_folder(user=admin_user, name="x" * 100)

    def test_create_folder_rejects_leading_trailing_whitespace(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = FolderService(repo)
        with pytest.raises(ValidationError):
            service.create_folder(user=admin_user, name="  spaces  ")

    def test_create_folder_rejects_internal_whitespace_via_wholly_blank(self, ctx, admin_user: CurrentUser):
        # Names are validated: leading/trailing whitespace is rejected, all-whitespace
        # is rejected, but a clean name with internal whitespace passes through.
        repo, _storage = ctx
        service = FolderService(repo)
        folder = service.create_folder(user=admin_user, name="with space")
        assert folder["name"] == "with space"

    def test_create_folder_rejects_invalid_scope(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = FolderService(repo)
        with pytest.raises(ValidationError):
            service.create_folder(user=admin_user, scope="bogus", name="Whatever")

    def test_create_folder_rejects_non_string_name(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = FolderService(repo)
        with pytest.raises(ValidationError):
            service.create_folder(user=admin_user, name=123)  # type: ignore[arg-type]

    def test_rename_rejects_non_assets_scope(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = FolderService(repo)
        # Create a videos-scope folder directly via the repo (service refuses to create them).
        folder_id = repo.create_folder(
            scope="videos", name="Old", description="", parent_id=None,
            project_id=None, created_by=repo.get_user_by_username("default-admin")["id"],
        )
        with pytest.raises(ValidationError):
            service.rename_folder(user=admin_user, folder_id=folder_id, name="New")

    def test_delete_rejects_non_assets_scope(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = FolderService(repo)
        folder_id = repo.create_folder(
            scope="videos", name="KeepMe", description="", parent_id=None,
            project_id=None, created_by=repo.get_user_by_username("default-admin")["id"],
        )
        with pytest.raises(ValidationError):
            service.delete_folder(user=admin_user, folder_id=folder_id)

    def test_create_folder_under_wrong_scope_parent_raises(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        # assets-scope folder (created via the service).
        service = FolderService(repo)
        assets_parent = service.create_folder(user=admin_user, name="Parent")

        # Trying to use the assets parent for a videos folder should fail.
        with pytest.raises(ValidationError):
            service.create_folder(user=admin_user, scope="videos", name="Child", parent_id=assets_parent["id"])


class TestProjectService:
    def test_create_project_strips_name(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = ProjectService(repo)
        project = service.create_project(user=admin_user, name="  Spaced  ", description=" x ")
        assert project["name"] == "Spaced"
        assert project["description"] == "x"

    def test_create_project_rejects_blank_name(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = ProjectService(repo)
        with pytest.raises(ValidationError):
            service.create_project(user=admin_user, name="   ", description="")

    def test_set_member_rejects_invalid_role(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = ProjectService(repo)
        project = service.create_project(user=admin_user, name="P", description="")
        with pytest.raises(ValidationError):
            service.set_member(user=admin_user, project_id=project["id"], member_user_id="x", role="superuser")

    def test_set_member_adds_initial_members(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = ProjectService(repo)
        other = repo.create_user(username="alice", display_name="A")
        project = service.create_project(
            user=admin_user, name="Team", description="",
            members=[{"user_id": other["id"], "role": "editor"}],
        )
        roles = sorted(m["role"] for m in project["members"])
        assert roles == ["editor", "owner"]

    def test_get_project_includes_role_and_members(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = ProjectService(repo)
        project = service.create_project(user=admin_user, name="Solo", description="")
        detail = service.get_project(user=admin_user, project_id=project["id"])
        assert detail["current_user_role"] == "owner"
        assert len(detail["members"]) == 1

    def test_get_project_blocks_non_member(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = ProjectService(repo)
        project = service.create_project(user=admin_user, name="Private", description="")
        outsider = CurrentUser(id=str(repo.create_user(username="bob", display_name="B")["id"]), username="bob", role="member")
        from workbench.errors import PermissionDeniedError
        with pytest.raises(PermissionDeniedError):
            service.get_project(user=outsider, project_id=project["id"])


class TestJobService:
    def test_create_job_validates_prompt(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = JobService(repo)
        with pytest.raises(ValidationError):
            service.create_job(
                user=admin_user, prompt="", duration_sec=4, resolution="720x1280",
                audio_start_sec=0, reference_image_asset_id=None,
                reference_audio_asset_id=None, replace_audio_asset_id=None,
            )

    def test_create_job_strips_prompt(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = JobService(repo)
        job = service.create_job(
            user=admin_user, prompt="  hello  ", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None,
            reference_audio_asset_id=None, replace_audio_asset_id=None,
        )
        assert job["prompt"] == "hello"

    @pytest.mark.parametrize("duration", [0, 61])
    def test_create_job_validates_duration(self, ctx, admin_user: CurrentUser, duration: int):
        repo, _storage = ctx
        service = JobService(repo)
        with pytest.raises(ValidationError):
            service.create_job(
                user=admin_user, prompt="x", duration_sec=duration, resolution="720x1280",
                audio_start_sec=0, reference_image_asset_id=None,
                reference_audio_asset_id=None, replace_audio_asset_id=None,
            )

    @pytest.mark.parametrize("resolution", ["", "640x480", "garbage"])
    def test_create_job_validates_resolution(self, ctx, admin_user: CurrentUser, resolution: str):
        repo, _storage = ctx
        service = JobService(repo)
        with pytest.raises(ValidationError):
            service.create_job(
                user=admin_user, prompt="x", duration_sec=4, resolution=resolution,
                audio_start_sec=0, reference_image_asset_id=None,
                reference_audio_asset_id=None, replace_audio_asset_id=None,
            )

    def test_create_job_succeeds_with_valid_input(self, ctx, admin_user: CurrentUser):
        repo, _storage = ctx
        service = JobService(repo)
        job = service.create_job(
            user=admin_user, prompt="render", duration_sec=8, resolution="1024x1024",
            audio_start_sec=0, reference_image_asset_id=None,
            reference_audio_asset_id=None, replace_audio_asset_id=None,
        )
        assert job["status"] == "queued"


class TestAssetService:
    def test_upload_asset_rejects_wrong_folder_scope(self, ctx, admin_user: CurrentUser):
        repo, storage = ctx
        service = AssetService(repo, storage)

        videos_folder_id = repo.create_folder(
            scope="videos", name="vids", description="", parent_id=None,
            project_id=None, created_by=repo.get_user_by_username("default-admin")["id"],
        )

        with pytest.raises(ValidationError):
            service.upload_asset(
                user=admin_user, kind="image", filename="x.png", mime_type="image/png",
                stream=BytesIO(b"x"), folder_id=videos_folder_id,
            )

    def test_upload_asset_writes_file_and_returns_metadata(self, ctx, admin_user: CurrentUser):
        repo, storage = ctx
        service = AssetService(repo, storage)

        result = service.upload_asset(
            user=admin_user, kind="image", filename="pixel.png", mime_type="image/png",
            stream=BytesIO(b"hello"), folder_id=None,
        )

        assert result["original_filename"] == "pixel.png"
        assert result["size_bytes"] == 5
        assert result["sha256"] == hashlib.sha256(b"hello").hexdigest()
        assert (storage.root / result["storage_key"]).read_bytes() == b"hello"

    def test_upload_asset_with_mismatched_project_folder_raises(self, ctx, admin_user: CurrentUser):
        repo, storage = ctx
        service = AssetService(repo, storage)

        project = ProjectService(repo).create_project(user=admin_user, name="P", description="")
        folder = FolderService(repo).create_folder(user=admin_user, name="F", project_id=project["id"])

        with pytest.raises(ValidationError):
            service.upload_asset(
                user=admin_user, kind="image", filename="x.png", mime_type="image/png",
                stream=BytesIO(b"x"), folder_id=folder["id"], project_id=None,
            )


class TestProjectWorkflowService:
    @pytest.fixture
    def fake_remote(self):
        class _Fake:
            def run_workflow(self, *_args, **_kwargs):
                return {"prompt_id": "prompt-1"}

            def get_result(self, *_args, **_kwargs):
                return {"pending": True, "results": []}

        return _Fake()

    def test_add_workflow_rejects_blank_id(self, ctx, admin_user: CurrentUser, fake_remote):
        repo, storage = ctx
        service = ProjectWorkflowService(repo, fake_remote, storage)  # type: ignore[arg-type]
        project = ProjectService(repo).create_project(user=admin_user, name="P", description="")

        with pytest.raises(ValidationError):
            service.add_workflow(user=admin_user, project_id=project["id"], workflow_id="   ", display_name="X", defaults={})

    def test_run_workflow_rejects_disabled(self, ctx, admin_user: CurrentUser, fake_remote):
        repo, storage = ctx
        service = ProjectWorkflowService(repo, fake_remote, storage)  # type: ignore[arg-type]
        project = ProjectService(repo).create_project(user=admin_user, name="P", description="")
        wf = repo.create_project_workflow(
            project_id=project["id"], workflow_id="wf", display_name=None,
            defaults={}, created_by=repo.get_user_by_username("default-admin")["id"],
        )

        # Disable the workflow directly via the connection.
        from workbench.db import connect_db
        with connect_db(repo.db_path) as conn:
            conn.execute("update project_workflows set enabled = false where id = %s", (wf["id"],))
            conn.commit()

        with pytest.raises(ValidationError):
            service.run_workflow(user=admin_user, project_id=project["id"], project_workflow_id=wf["id"], input_values={})

    def test_refresh_run_without_prompt_id_short_circuits(self, ctx, admin_user: CurrentUser, fake_remote):
        repo, storage = ctx
        service = ProjectWorkflowService(repo, fake_remote, storage)  # type: ignore[arg-type]
        project = ProjectService(repo).create_project(user=admin_user, name="P", description="")
        wf = repo.create_project_workflow(
            project_id=project["id"], workflow_id="wf", display_name=None,
            defaults={}, created_by=repo.get_user_by_username("default-admin")["id"],
        )
        run = repo.create_remote_workflow_run(
            project_id=project["id"], project_workflow_id=wf["id"], workflow_id="wf",
            input_values={}, created_by=repo.get_user_by_username("default-admin")["id"],
        )
        # No prompt_id set; refresh should return the run unchanged.
        refreshed = service.refresh_run(user=admin_user, project_id=project["id"], run_id=run["id"])
        assert refreshed["prompt_id"] is None
        assert refreshed["status"] == "queued"

    def test_refresh_run_for_other_project_rejects(self, ctx, admin_user: CurrentUser, fake_remote):
        repo, storage = ctx
        service = ProjectWorkflowService(repo, fake_remote, storage)  # type: ignore[arg-type]
        project_a = ProjectService(repo).create_project(user=admin_user, name="A", description="")
        project_b = ProjectService(repo).create_project(user=admin_user, name="B", description="")
        wf_a = repo.create_project_workflow(
            project_id=project_a["id"], workflow_id="wf", display_name=None,
            defaults={}, created_by=repo.get_user_by_username("default-admin")["id"],
        )
        run = repo.create_remote_workflow_run(
            project_id=project_a["id"], project_workflow_id=wf_a["id"], workflow_id="wf",
            input_values={}, created_by=repo.get_user_by_username("default-admin")["id"],
        )
        with pytest.raises(ValidationError):
            service.refresh_run(user=admin_user, project_id=project_b["id"], run_id=run["id"])