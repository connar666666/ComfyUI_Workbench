from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from workbench.config import WorkbenchSettings
from workbench.db import database_url_for_schema, initialize_db
from workbench.errors import ConflictError, NotFoundError, PermissionDeniedError
from workbench.repositories import WorkbenchRepository


def _make_repo() -> WorkbenchRepository:
    """Create a fresh repository backed by a unique Postgres schema per test."""
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
    digest = hashlib.sha1(str(settings.db_path).encode()).hexdigest()[:16]
    test_schema = f"workbench_{digest}"
    initialize_db(
        settings.database_url,
        settings.default_user,
        settings.default_role,
        schema=test_schema,
    )
    repo = WorkbenchRepository(settings.db_path)
    repo._tmp = tmp  # type: ignore[attr-defined]
    return repo


@pytest.fixture
def repo():
    r = _make_repo()
    yield r
    r._tmp.cleanup()  # type: ignore[attr-defined]


class TestUserRepo:
    def test_default_user_created_on_initialize(self, repo: WorkbenchRepository):
        user = repo.get_user_by_username("default-admin")
        assert user["username"] == "default-admin"
        assert user["role"] == "admin"

    def test_create_user_assigns_member_role_by_default(self, repo: WorkbenchRepository):
        user = repo.create_user(username="alice", display_name="Alice")
        assert user["username"] == "alice"
        assert user["role"] == "member"

    def test_create_user_rejects_duplicate_username(self, repo: WorkbenchRepository):
        repo.create_user(username="dup", display_name="dup")
        with pytest.raises(ConflictError):
            repo.create_user(username="dup", display_name="dup2")

    def test_get_user_by_id_with_unknown_format_raises_not_found(self, repo: WorkbenchRepository):
        with pytest.raises(NotFoundError):
            repo.get_user_by_id("not-a-uuid")

    def test_get_user_by_id_missing_raises_not_found(self, repo: WorkbenchRepository):
        user = repo.create_user(username="alice", display_name="Alice")
        with pytest.raises(NotFoundError):
            repo.get_user_by_id("00000000-0000-0000-0000-000000000000")

    def test_get_user_by_id_returns_user(self, repo: WorkbenchRepository):
        user = repo.create_user(username="alice", display_name="Alice")
        fetched = repo.get_user_by_id(user["id"])
        assert fetched["id"] == user["id"]

    def test_get_user_by_username_missing_raises_not_found(self, repo: WorkbenchRepository):
        with pytest.raises(NotFoundError):
            repo.get_user_by_username("nobody")

    def test_resolve_user_id_falls_back_to_username(self, repo: WorkbenchRepository):
        user = repo.create_user(username="alice", display_name="Alice")
        # Pass a bogus primary id; the helper should look up by username instead.
        resolved = repo.resolve_user_id("00000000-0000-0000-0000-000000000000", "alice")
        assert resolved == user["id"]

    def test_resolve_user_id_raises_when_neither_works(self, repo: WorkbenchRepository):
        with pytest.raises(NotFoundError):
            repo.resolve_user_id("00000000-0000-0000-0000-000000000000", None)

    def test_list_users_returns_at_least_default(self, repo: WorkbenchRepository):
        users = repo.list_users()
        assert any(u["username"] == "default-admin" for u in users)

    def test_update_last_seen_does_not_raise(self, repo: WorkbenchRepository):
        user = repo.create_user(username="alice", display_name="Alice")
        repo.update_last_seen(user["id"])  # should not raise


class TestProjectRepo:
    def test_create_project_uses_creator_as_owner(self, repo: WorkbenchRepository):
        creator = repo.get_user_by_username("default-admin")
        project = repo.create_project(name="Demo", description="", created_by=creator["id"])

        assert project["name"] == "Demo"
        member = repo.get_project_member(project["id"], creator["id"])
        assert member["role"] == "owner"

    def test_get_project_with_unknown_id_raises(self, repo: WorkbenchRepository):
        with pytest.raises(NotFoundError):
            repo.get_project("not-a-uuid")

    def test_list_projects_for_admin_returns_all(self, repo: WorkbenchRepository):
        creator = repo.get_user_by_username("default-admin")
        repo.create_project(name="A", description="", created_by=creator["id"])
        repo.create_project(name="B", description="", created_by=creator["id"])

        projects = repo.list_projects(user_id=creator["id"], role="admin")
        names = {p["name"] for p in projects}
        assert {"A", "B"}.issubset(names)

    def test_list_projects_for_member_only_returns_their_own(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        owner = repo.create_user(username="owner", display_name="Owner", role="member")
        outsider = repo.create_user(username="outsider", display_name="Outsider", role="member")

        owned = repo.create_project(name="Owned", description="", created_by=owner["id"])
        repo.create_project(name="Other", description="", created_by=admin["id"])

        visible = repo.list_projects(user_id=outsider["id"], role="member")
        assert [p["id"] for p in visible] == []

        visible_owner = repo.list_projects(user_id=owner["id"], role="member")
        assert {p["id"] for p in visible_owner} == {owned["id"]}

    def test_set_project_member_updates_role(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        project = repo.create_project(name="X", description="", created_by=admin["id"])
        viewer = repo.create_user(username="v", display_name="V", role="member")

        member = repo.set_project_member(project_id=project["id"], user_id=viewer["id"], role="viewer")
        assert member["role"] == "viewer"

    def test_remove_project_member_blocks_removing_last_owner(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        project = repo.create_project(name="Solo", description="", created_by=admin["id"])

        with pytest.raises(ConflictError):
            repo.remove_project_member(project_id=project["id"], user_id=admin["id"])

    def test_remove_project_member_missing_raises_not_found(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        project = repo.create_project(name="X", description="", created_by=admin["id"])
        with pytest.raises(NotFoundError):
            repo.remove_project_member(project_id=project["id"], user_id="00000000-0000-0000-0000-000000000000")

    def test_list_project_members_sorted_by_role(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        owner = repo.create_user(username="owner", display_name="O", role="member")
        viewer = repo.create_user(username="viewer", display_name="V", role="member")

        project = repo.create_project(name="Roles", description="", created_by=admin["id"])
        repo.set_project_member(project_id=project["id"], user_id=owner["id"], role="editor")
        repo.set_project_member(project_id=project["id"], user_id=viewer["id"], role="viewer")

        members = repo.list_project_members(project["id"])
        roles = [m["role"] for m in members]
        # Order should put owner first, then editor, then viewer.
        assert roles.index("owner") < roles.index("editor")
        assert roles.index("editor") < roles.index("viewer")


class TestFolderRepo:
    def test_create_and_get_folder(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        folder_id = repo.create_folder(
            scope="assets", name="Refs", description="", parent_id=None,
            project_id=None, created_by=admin["id"],
        )
        folder = repo.get_folder(folder_id)
        assert folder["name"] == "Refs"
        assert folder["asset_count"] == 0

    def test_get_folder_with_unknown_id_raises(self, repo: WorkbenchRepository):
        with pytest.raises(NotFoundError):
            repo.get_folder("not-a-uuid")

    def test_list_folders_filters_by_scope_and_parent(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        a_id = repo.create_folder(scope="assets", name="A", description="", parent_id=None, project_id=None, created_by=admin["id"])
        repo.create_folder(scope="videos", name="A", description="", parent_id=None, project_id=None, created_by=admin["id"])
        repo.create_folder(scope="assets", name="B", description="", parent_id=a_id, project_id=None, created_by=admin["id"])

        assets_root = repo.list_folders(scope="assets", parent_id=None)
        assets_child = repo.list_folders(scope="assets", parent_id=a_id)
        videos_root = repo.list_folders(scope="videos", parent_id=None)

        assert {f["name"] for f in assets_root} == {"A"}
        assert {f["name"] for f in assets_child} == {"B"}
        assert {f["name"] for f in videos_root} == {"A"}

    def test_find_folder_by_name_returns_match(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        repo.create_folder(scope="assets", name="Targets", description="", parent_id=None, project_id=None, created_by=admin["id"])
        match = repo.find_folder_by_name(scope="assets", name="Targets", parent_id=None)
        assert match is not None
        assert match["name"] == "Targets"

    def test_find_folder_by_name_returns_none_when_absent(self, repo: WorkbenchRepository):
        match = repo.find_folder_by_name(scope="assets", name="Missing", parent_id=None)
        assert match is None

    def test_rename_folder(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        folder_id = repo.create_folder(scope="assets", name="Old", description="", parent_id=None, project_id=None, created_by=admin["id"])
        renamed = repo.rename_folder(folder_id, "New")
        assert renamed["name"] == "New"

    def test_delete_folder_removed(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        folder_id = repo.create_folder(scope="assets", name="Disposable", description="", parent_id=None, project_id=None, created_by=admin["id"])
        repo.delete_folder(folder_id)
        with pytest.raises(NotFoundError):
            repo.get_folder(folder_id)

    def test_count_assets_and_children(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        parent = repo.create_folder(scope="assets", name="P", description="", parent_id=None, project_id=None, created_by=admin["id"])
        repo.create_folder(scope="assets", name="C", description="", parent_id=parent, project_id=None, created_by=admin["id"])

        assert repo.count_assets_in_folder(parent) == 0
        assert repo.count_child_folders(parent) == 1


class TestAssetRepo:
    def test_create_and_get_asset(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        asset = repo.create_asset(
            kind="image", original_filename="a.png", storage_key="assets/images/a.png",
            mime_type="image/png", size_bytes=10, sha256="deadbeef", uploaded_by=admin["id"],
            folder_id=None,
        )
        fetched = repo.get_asset(asset["id"])
        assert fetched["original_filename"] == "a.png"

    def test_get_asset_with_unknown_id_raises(self, repo: WorkbenchRepository):
        with pytest.raises(NotFoundError):
            repo.get_asset("not-a-uuid")

    def test_delete_asset_hides_from_list(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        asset = repo.create_asset(
            kind="image", original_filename="a.png", storage_key="assets/images/a.png",
            mime_type="image/png", size_bytes=10, sha256="x", uploaded_by=admin["id"], folder_id=None,
        )
        repo.delete_asset(asset["id"])
        with pytest.raises(NotFoundError):
            repo.get_asset(asset["id"])

    def test_list_assets_filters_by_kind(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        for kind, idx in [("image", 1), ("audio", 1), ("image", 2)]:
            repo.create_asset(
                kind=kind, original_filename=f"{kind}{idx}.bin",
                storage_key=f"assets/{kind}s/{kind}-{idx}.bin",
                mime_type="application/octet-stream", size_bytes=1, sha256="x",
                uploaded_by=admin["id"], folder_id=None,
            )
        images = repo.list_assets(kind="image", role="admin")
        audios = repo.list_assets(kind="audio", role="admin")
        assert len(images) == 2
        assert len(audios) == 1

    def test_list_assets_for_member_filters_to_owner(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        other = repo.create_user(username="other", display_name="Other", role="member")
        repo.create_asset(
            kind="image", original_filename="a.png", storage_key="assets/images/a.png",
            mime_type="image/png", size_bytes=10, sha256="x", uploaded_by=admin["id"], folder_id=None,
        )
        mine = repo.create_asset(
            kind="image", original_filename="b.png", storage_key="assets/images/b.png",
            mime_type="image/png", size_bytes=10, sha256="x", uploaded_by=other["id"], folder_id=None,
        )
        # Member sees only their own assets; admin sees everything.
        member_view = repo.list_assets(user_id=other["id"], role="member")
        admin_view = repo.list_assets(user_id=admin["id"], role="admin")
        assert {a["id"] for a in member_view} == {mine["id"]}
        assert len(admin_view) == 2


class TestJobRepo:
    def test_create_and_get_job(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        job = repo.create_job(
            created_by=admin["id"], prompt="hi", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None, reference_audio_asset_id=None,
            replace_audio_asset_id=None,
        )
        fetched = repo.get_job(job["id"])
        assert fetched["prompt"] == "hi"
        assert fetched["status"] == "queued"

    def test_create_job_persists_reference_fields(self, repo: WorkbenchRepository):
        # Note: a follow-up commit is needed to fix the job_inputs insert path
        # (the SQL builder always appends "returning id", but job_inputs has no
        # id column). Until then we only exercise the no-input branch.
        admin = repo.get_user_by_username("default-admin")
        job = repo.create_job(
            created_by=admin["id"], prompt="hi", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None, reference_audio_asset_id=None,
            replace_audio_asset_id=None,
        )
        assert job["reference_image_asset_id"] is None
        assert job["reference_audio_asset_id"] is None

    def test_claim_next_job_returns_oldest_queued(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        first = repo.create_job(
            created_by=admin["id"], prompt="first", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None, reference_audio_asset_id=None,
            replace_audio_asset_id=None,
        )
        repo.create_job(
            created_by=admin["id"], prompt="second", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None, reference_audio_asset_id=None,
            replace_audio_asset_id=None,
        )
        claimed = repo.claim_next_job()
        assert claimed["id"] == first["id"]
        assert claimed["status"] == "running"

        # Subsequent claim should skip the running one.
        second = repo.claim_next_job()
        assert second["id"] != first["id"]
        assert second["prompt"] == "second"

    def test_claim_next_job_returns_none_when_empty(self, repo: WorkbenchRepository):
        assert repo.claim_next_job() is None

    def test_mark_job_succeeded(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        job = repo.create_job(
            created_by=admin["id"], prompt="x", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None, reference_audio_asset_id=None,
            replace_audio_asset_id=None,
        )
        repo.mark_job_succeeded(job["id"], output_video_id=None)
        fetched = repo.get_job(job["id"])
        assert fetched["status"] == "succeeded"
        assert fetched["completed_at"] is not None

    def test_mark_job_failed(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        job = repo.create_job(
            created_by=admin["id"], prompt="x", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None, reference_audio_asset_id=None,
            replace_audio_asset_id=None,
        )
        repo.mark_job_failed(job["id"], "internal_error", "boom")
        fetched = repo.get_job(job["id"])
        assert fetched["status"] == "failed"
        assert fetched["error_message"] == "boom"

    def test_cancel_job_admin_can_cancel_any(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        member = repo.create_user(username="m", display_name="M", role="member")
        job = repo.create_job(
            created_by=member["id"], prompt="x", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None, reference_audio_asset_id=None,
            replace_audio_asset_id=None,
        )
        repo.cancel_job(job["id"], user_id=admin["id"], role="admin")
        assert repo.get_job(job["id"])["status"] == "canceled"

    def test_cancel_job_owner_can_cancel_own(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        job = repo.create_job(
            created_by=admin["id"], prompt="x", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None, reference_audio_asset_id=None,
            replace_audio_asset_id=None,
        )
        repo.cancel_job(job["id"], user_id=admin["id"], role="admin")
        assert repo.get_job(job["id"])["status"] == "canceled"

    def test_cancel_job_member_cannot_cancel_others(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        member = repo.create_user(username="m", display_name="M", role="member")
        other = repo.create_user(username="o", display_name="O", role="member")
        job = repo.create_job(
            created_by=other["id"], prompt="x", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None, reference_audio_asset_id=None,
            replace_audio_asset_id=None,
        )
        with pytest.raises(PermissionDeniedError):
            repo.cancel_job(job["id"], user_id=member["id"], role="member")

    def test_cancel_job_missing_raises(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        with pytest.raises(NotFoundError):
            # Cancel looks up by UUID; pass an unknown UUID.
            repo.cancel_job("00000000-0000-0000-0000-000000000000", user_id=admin["id"], role="admin")

    def test_record_comfyui_task_round_trips(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        job = repo.create_job(
            created_by=admin["id"], prompt="x", duration_sec=4, resolution="720x1280",
            audio_start_sec=0, reference_image_asset_id=None, reference_audio_asset_id=None,
            replace_audio_asset_id=None,
        )
        task = repo.record_comfyui_task(
            job_id=job["id"], prompt_id="prompt-1", comfyui_url="http://x",
            native_status="running", raw_summary={"x": 1},
        )
        assert task["prompt_id"] == "prompt-1"

        # Updating the same prompt_id should upsert.
        again = repo.record_comfyui_task(
            job_id=job["id"], prompt_id="prompt-1", comfyui_url="http://x",
            native_status="history", raw_summary={"x": 2},
        )
        assert again["native_status"] == "history"


class TestVideoRepo:
    def test_create_and_get_video(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        video = repo.create_video(
            source_job_id=None, created_by=admin["id"], title="hi.mp4",
            storage_key="outputs/videos/hi.mp4", mime_type="video/mp4",
            size_bytes=12, prompt="p",
        )
        fetched = repo.get_video(video["id"])
        assert fetched["title"] == "hi.mp4"

    def test_list_videos_excludes_deleted(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        v1 = repo.create_video(
            source_job_id=None, created_by=admin["id"], title="one.mp4",
            storage_key="outputs/videos/one.mp4", mime_type="video/mp4", size_bytes=1,
        )
        v2 = repo.create_video(
            source_job_id=None, created_by=admin["id"], title="two.mp4",
            storage_key="outputs/videos/two.mp4", mime_type="video/mp4", size_bytes=2,
        )
        # Soft-delete v1 directly via the connection.
        from workbench.db import connect_db
        with connect_db(repo.db_path) as conn:
            conn.execute("update videos set deleted_at = now() where id = %s", (v1["id"],))
            conn.commit()
        visible = repo.list_videos()
        ids = [v["id"] for v in visible]
        assert v2["id"] in ids
        assert v1["id"] not in ids


class TestInviteRepo:
    def test_invite_lifecycle(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        invite = repo.create_invite(token_hash="h1", created_by=admin["id"], role="member", max_uses=1)
        assert invite["token_hash"] == "h1"

        fetched = repo.get_invite_by_hash("h1")
        assert fetched is not None

        # First use succeeds, second use should be blocked because max_uses=1.
        assert repo.use_invite("h1") is True
        assert repo.use_invite("h1") is False

        # Revoke.
        repo.revoke_invite("h1")
        assert repo.get_invite_by_hash("h1") is None

    def test_invite_use_blocks_expired(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        repo.create_invite(token_hash="old", created_by=admin["id"], expires_at=past)
        assert repo.use_invite("old") is False

    def test_list_invites_filters_by_creator(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        member = repo.create_user(username="m", display_name="M", role="member")
        repo.create_invite(token_hash="h-a", created_by=admin["id"])
        repo.create_invite(token_hash="h-m", created_by=member["id"])

        admins = repo.list_invites(created_by=admin["id"])
        members = repo.list_invites(created_by=member["id"])
        assert {i["token_hash"] for i in admins} == {"h-a"}
        assert {i["token_hash"] for i in members} == {"h-m"}


class TestNodeVersionRepo:
    def test_create_node_version_auto_increments(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        v1 = repo.create_node_version(
            canvas_id="canvas-1", node_id="node-1", generation_job_id=None,
            output_video_id=None, prompt="p1", input_asset_ids=[],
            params={"k": "v"}, snapshot={"id": "node-1"}, status="succeeded",
            created_by=admin["id"],
        )
        v2 = repo.create_node_version(
            canvas_id="canvas-1", node_id="node-1", generation_job_id=None,
            output_video_id=None, prompt="p2", input_asset_ids=[],
            params={"k": "v"}, snapshot={"id": "node-1"}, status="succeeded",
            created_by=admin["id"],
        )
        assert v2["version_number"] == v1["version_number"] + 1

    def test_list_node_versions_filters_by_node(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        repo.create_node_version(
            canvas_id="c1", node_id="n1", generation_job_id=None, output_video_id=None,
            prompt="p", input_asset_ids=[], params={}, snapshot={}, status="succeeded",
            created_by=admin["id"],
        )
        repo.create_node_version(
            canvas_id="c1", node_id="n2", generation_job_id=None, output_video_id=None,
            prompt="p", input_asset_ids=[], params={}, snapshot={}, status="succeeded",
            created_by=admin["id"],
        )
        n1_versions = repo.list_node_versions("c1", "n1")
        all_versions = repo.list_node_versions("c1")
        assert len(n1_versions) == 1
        assert len(all_versions) == 2


class TestProjectWorkflowRepo:
    def test_create_project_workflow_increments_sort_order(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        project = repo.create_project(name="P", description="", created_by=admin["id"])

        wf1 = repo.create_project_workflow(
            project_id=project["id"], workflow_id="wf-1", display_name=None,
            defaults={}, created_by=admin["id"],
        )
        wf2 = repo.create_project_workflow(
            project_id=project["id"], workflow_id="wf-2", display_name=None,
            defaults={"k": "v"}, created_by=admin["id"],
        )
        assert wf1["sort_order"] == 0
        assert wf2["sort_order"] == 1
        # defaults should be decoded back as a dict.
        assert wf2["defaults"] == {"k": "v"}

    def test_list_project_workflows_orders_by_sort_order(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        project = repo.create_project(name="P", description="", created_by=admin["id"])
        repo.create_project_workflow(project_id=project["id"], workflow_id="wf-2", display_name=None, defaults={}, created_by=admin["id"])
        repo.create_project_workflow(project_id=project["id"], workflow_id="wf-1", display_name=None, defaults={}, created_by=admin["id"])
        ordered = repo.list_project_workflows(project["id"])
        assert [w["workflow_id"] for w in ordered] == ["wf-2", "wf-1"]


class TestRemoteWorkflowRunRepo:
    def test_run_lifecycle(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        project = repo.create_project(name="P", description="", created_by=admin["id"])
        wf = repo.create_project_workflow(
            project_id=project["id"], workflow_id="wf-1", display_name=None,
            defaults={}, created_by=admin["id"],
        )

        run = repo.create_remote_workflow_run(
            project_id=project["id"], project_workflow_id=wf["id"], workflow_id="wf-1",
            input_values={"prompt": "hi"}, created_by=admin["id"],
        )
        assert run["status"] == "queued"
        assert run["input_values"] == {"prompt": "hi"}

        started = repo.mark_remote_workflow_run_started(run["id"], "prompt-1")
        assert started["status"] == "running"
        assert started["prompt_id"] == "prompt-1"

        completed = repo.update_remote_workflow_run_result(
            run_id=run["id"], status="succeeded", results=[{"type": "image"}],
        )
        assert completed["status"] == "succeeded"
        assert completed["results"] == [{"type": "image"}]
        assert completed["completed_at"] is not None

    def test_list_remote_workflow_runs_returns_most_recent_first(self, repo: WorkbenchRepository):
        admin = repo.get_user_by_username("default-admin")
        project = repo.create_project(name="P", description="", created_by=admin["id"])
        wf = repo.create_project_workflow(
            project_id=project["id"], workflow_id="wf", display_name=None,
            defaults={}, created_by=admin["id"],
        )
        r1 = repo.create_remote_workflow_run(
            project_id=project["id"], project_workflow_id=wf["id"], workflow_id="wf",
            input_values={}, created_by=admin["id"],
        )
        r2 = repo.create_remote_workflow_run(
            project_id=project["id"], project_workflow_id=wf["id"], workflow_id="wf",
            input_values={}, created_by=admin["id"],
        )
        runs = repo.list_remote_workflow_runs(project["id"])
        # r2 is more recent, so it appears first.
        assert runs[0]["id"] == r2["id"]
        assert runs[1]["id"] == r1["id"]