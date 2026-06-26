from __future__ import annotations

import tempfile
import unittest
import asyncio
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from workbench.api import create_app
from workbench.auth import CurrentUser, create_access_token, get_current_user, hash_password
from workbench.config import WorkbenchSettings
from workbench.repositories import WorkbenchRepository
from workbench.sse import _sse_auth, get_event_bus


class _FakeLiveblocksResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"token": "liveblocks-token"}


class _FakeSseRequest:
    def __init__(self, token: str):
        self.query_params = {"authorization": f"Bearer {token}"}
        self.headers = {}


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root_dir = Path(self.tempdir.name) / "root"
        self.root_dir.mkdir()
        self.settings = WorkbenchSettings(
            root_dir=self.root_dir,
            db_path=self.root_dir / "workbench.sqlite",
            comfyui_url="http://127.0.0.1:8188",
            zealman_base_url="https://zealman.example.com",
            zealman_token="secret-token",
            default_user="owner",
            default_role="admin",
            jwt_secret="test-secret",
            jwt_expiry_hours=24,
            invite_token_bytes=8,
            invite_expiry_days=7,
            liveblocks_secret_key="liveblocks-secret",
        )
        self.app = create_app(self.settings)
        self.repo = WorkbenchRepository(self.settings.db_path)
        self.owner = self.repo.get_user_by_username("owner")
        self.current_user = CurrentUser(id=self.owner["id"], username="owner", role="admin")
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def tearDown(self):
        self.tempdir.cleanup()

    def _project(self, name: str = "Contract Project") -> dict:
        response = self.client.post("/api/projects", json={"name": name, "description": "API contract"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _asset(self, project_id: str | None = None) -> dict:
        url = f"/api/projects/{project_id}/assets" if project_id else "/api/assets"
        response = self.client.post(
            url,
            data={"kind": "image"},
            files={"file": ("sample.png", BytesIO(b"image-bytes"), "image/png")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_health_users_liveblocks_and_sse_endpoints_accept_uuid_users(self):
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})

        users = self.client.get("/api/users")
        self.assertEqual(users.status_code, 200, users.text)
        self.assertEqual(users.json()[0]["username"], "owner")

        resolve = self.client.post("/api/liveblocks/resolve-users", json={"userIds": [self.owner["id"], "missing"]})
        self.assertEqual(resolve.status_code, 200, resolve.text)
        self.assertEqual(resolve.json()[0]["name"], "owner")

        with patch("workbench.api.httpx.post", return_value=_FakeLiveblocksResponse()) as liveblocks_post:
            auth = self.client.post("/api/liveblocks-auth", json={"room": "canvas:contract"})
        self.assertEqual(auth.status_code, 200, auth.text)
        self.assertEqual(auth.json(), {"token": "liveblocks-token"})
        self.assertEqual(liveblocks_post.call_args.kwargs["json"]["userId"], self.owner["id"])

        token = create_access_token(self.owner["id"], self.owner["username"], self.owner["role"])
        self.assertTrue(any(getattr(route, "path", None) == "/api/events" for route in self.app.routes))
        sse_user = asyncio.run(_sse_auth(_FakeSseRequest(token)))  # type: ignore[arg-type]
        self.assertEqual(sse_user.id, self.owner["id"])

    def test_auth_endpoints_cover_register_login_refresh_me_invites_join_and_revoke(self):
        import workbench.routes_auth as routes_auth

        self.app.dependency_overrides.pop(get_current_user, None)
        owner_token = create_access_token(self.owner["id"], self.owner["username"], self.owner["role"])
        owner_headers = {"Authorization": f"Bearer {owner_token}"}
        with patch.object(routes_auth, "_get_repo", return_value=self.repo):
            register = self.client.post(
                "/api/auth/register",
                json={"username": "contract-user", "password": "pass1234", "display_name": "Contract User"},
            )
            self.assertEqual(register.status_code, 200, register.text)

            login = self.client.post("/api/auth/login", json={"username": "contract-user", "password": "pass1234"})
            self.assertEqual(login.status_code, 200, login.text)
            refresh = self.client.post("/api/auth/refresh", json={"refresh_token": login.json()["refresh_token"]})
            self.assertEqual(refresh.status_code, 200, refresh.text)

            token = login.json()["access_token"]
            me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(me.status_code, 200, me.text)
            self.assertEqual(me.json()["username"], "contract-user")

            invite = self.client.post(
                "/api/auth/invites",
                headers=owner_headers,
                json={"role": "member", "max_uses": 1},
            )
            self.assertEqual(invite.status_code, 200, invite.text)
            invites = self.client.get("/api/auth/invites", headers=owner_headers)
            self.assertEqual(invites.status_code, 200, invites.text)
            self.assertEqual(len(invites.json()), 1)

            join = self.client.post(
                "/api/auth/join",
                json={"token": invite.json()["token"], "username": "joined-user", "display_name": "Joined User"},
            )
            self.assertEqual(join.status_code, 200, join.text)

            second_invite = self.client.post("/api/auth/invites", headers=owner_headers, json={"role": "member"})
            invite_id = self.client.get("/api/auth/invites", headers=owner_headers).json()[0]["id"]
            self.assertEqual(second_invite.status_code, 200, second_invite.text)
            revoke = self.client.post(f"/api/auth/invites/{invite_id}/revoke", headers=owner_headers)
            self.assertEqual(revoke.status_code, 200, revoke.text)
            self.assertEqual(revoke.json(), {"status": "revoked"})

    def test_assets_folders_files_jobs_canvas_and_videos_endpoints(self):
        folder = self.client.post("/api/folders", json={"scope": "assets", "name": "Contract Folder"})
        self.assertEqual(folder.status_code, 200, folder.text)
        folder_id = folder.json()["id"]

        folders = self.client.get("/api/folders")
        self.assertEqual(folders.status_code, 200, folders.text)
        self.assertEqual(folders.json()[0]["id"], folder_id)

        renamed = self.client.patch(f"/api/folders/{folder_id}", json={"name": "Renamed Folder"})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["name"], "Renamed Folder")

        asset = self.client.post(
            "/api/assets",
            data={"kind": "image", "folder_id": folder_id},
            files={"file": ("global.png", BytesIO(b"global-bytes"), "image/png")},
        )
        self.assertEqual(asset.status_code, 200, asset.text)
        asset_id = asset.json()["id"]

        assets = self.client.get(f"/api/assets?folder_id={folder_id}")
        self.assertEqual(assets.status_code, 200, assets.text)
        self.assertEqual(assets.json()[0]["id"], asset_id)

        file_response = self.client.get(f"/files/assets/{asset_id}")
        self.assertEqual(file_response.status_code, 200, file_response.text)
        self.assertEqual(file_response.content, b"global-bytes")

        delete_asset = self.client.delete(f"/api/assets/{asset_id}")
        self.assertEqual(delete_asset.status_code, 200, delete_asset.text)
        self.assertEqual(delete_asset.json(), {"ok": True})
        self.assertEqual(self.client.get(f"/files/assets/{asset_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/assets?folder_id={folder_id}").json(), [])

        job = self.client.post(
            "/api/jobs",
            json={"prompt": "render a frame", "duration_sec": 4, "resolution": "720x1280"},
        )
        self.assertEqual(job.status_code, 200, job.text)
        job_id = job.json()["id"]

        jobs = self.client.get("/api/jobs")
        self.assertEqual(jobs.status_code, 200, jobs.text)
        self.assertEqual(jobs.json()[0]["id"], job_id)

        canceled = self.client.post(f"/api/jobs/{job_id}/cancel")
        self.assertEqual(canceled.status_code, 200, canceled.text)
        self.assertEqual(canceled.json()["status"], "canceled")

        version = self.repo.create_node_version(
            canvas_id="contract-canvas",
            node_id="node-1",
            generation_job_id=None,
            output_video_id=None,
            prompt="render a frame",
            input_asset_ids=[asset_id],
            params={"resolution": "720x1280"},
            snapshot={"id": "node-1"},
            status="succeeded",
            created_by=self.owner["id"],
        )
        canvas_versions = self.client.get("/api/canvas/contract-canvas/versions")
        self.assertEqual(canvas_versions.status_code, 200, canvas_versions.text)
        self.assertEqual(canvas_versions.json()[0]["id"], version["id"])

        node_versions = self.client.get("/api/canvas/contract-canvas/nodes/node-1/versions")
        self.assertEqual(node_versions.status_code, 200, node_versions.text)
        self.assertEqual(node_versions.json()[0]["node_id"], "node-1")

        video_key = "outputs/videos/contract.mp4"
        video_path = self.root_dir / video_key
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"video-bytes")
        video = self.repo.create_video(
            source_job_id=None,
            created_by=self.owner["id"],
            title="contract.mp4",
            storage_key=video_key,
            mime_type="video/mp4",
            size_bytes=11,
            prompt="render a frame",
        )

        videos = self.client.get("/api/videos")
        self.assertEqual(videos.status_code, 200, videos.text)
        self.assertEqual(videos.json()[0]["id"], video["id"])

        video_file = self.client.get(f"/files/videos/{video['id']}")
        self.assertEqual(video_file.status_code, 200, video_file.text)
        self.assertEqual(video_file.content, b"video-bytes")

        deleted = self.client.delete(f"/api/folders/{folder_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)

    def test_asset_uploaded_sse_payload_is_json_serializable(self):
        queue = asyncio.run(get_event_bus().subscribe("admin"))
        try:
            project = self._project("SSE payload project")
            asset = self._asset(project["id"])
            self.assertEqual(asset["project_id"], project["id"])

            payload = queue.get_nowait()
            json.dumps(payload, ensure_ascii=False)
        finally:
            get_event_bus().unsubscribe(queue)

    def test_project_and_remote_workflow_endpoints(self):
        viewer = self.repo.create_user(username="viewer-contract", display_name="Viewer", role="member")
        project = self._project()
        project_id = project["id"]

        projects = self.client.get("/api/projects")
        self.assertEqual(projects.status_code, 200, projects.text)
        self.assertEqual(projects.json()[0]["id"], project_id)

        detail = self.client.get(f"/api/projects/{project_id}")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["id"], project_id)

        member = self.client.put(f"/api/projects/{project_id}/members/{viewer['id']}", json={"role": "viewer"})
        self.assertEqual(member.status_code, 200, member.text)
        self.assertEqual(member.json()["role"], "viewer")

        removed = self.client.delete(f"/api/projects/{project_id}/members/{viewer['id']}")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(removed.json(), {"ok": True})

        asset = self._asset(project_id)
        project_assets = self.client.get(f"/api/projects/{project_id}/assets")
        self.assertEqual(project_assets.status_code, 200, project_assets.text)
        self.assertEqual(project_assets.json()[0]["id"], asset["id"])

        with patch("workbench.remote_workflows.RemoteWorkflowClient.list_workflows", return_value=[{"id": "wf-1"}]):
            remote_list = self.client.get("/api/remote-workflows")
        self.assertEqual(remote_list.status_code, 200, remote_list.text)
        self.assertEqual(remote_list.json(), {"workflows": [{"id": "wf-1"}]})

        with patch("workbench.remote_workflows.RemoteWorkflowClient.upload_file", return_value={"filename": "input.png"}):
            upload = self.client.post(
                "/api/remote-workflows/uploads",
                data={"overwrite": "true"},
                files={"file": ("input.png", BytesIO(b"input"), "image/png")},
            )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(upload.json(), {"filename": "input.png"})

        with patch("workbench.remote_workflows.RemoteWorkflowClient.get_workflow", return_value={"id": "wf-1"}):
            workflow_detail = self.client.get("/api/remote-workflows/wf-1")
        self.assertEqual(workflow_detail.status_code, 200, workflow_detail.text)
        self.assertEqual(workflow_detail.json(), {"id": "wf-1"})

        with patch("workbench.remote_workflows.RemoteWorkflowClient.run_workflow", return_value={"prompt_id": "prompt-1"}):
            remote_run = self.client.post("/api/remote-workflows/wf-1/run", json={"input_values": {"prompt": "hello"}})
        self.assertEqual(remote_run.status_code, 200, remote_run.text)
        self.assertEqual(remote_run.json(), {"prompt_id": "prompt-1"})

        with patch("workbench.remote_workflows.RemoteWorkflowClient.get_result", return_value={"pending": False, "results": []}):
            remote_result = self.client.get("/api/remote-workflows/runs/prompt-1")
        self.assertEqual(remote_result.status_code, 200, remote_result.text)
        self.assertEqual(remote_result.json(), {"pending": False, "results": []})

        selected = self.client.post(
            f"/api/projects/{project_id}/workflows",
            json={"workflow_id": "wf-1", "display_name": "Workflow 1", "defaults": {"prompt": "base"}},
        )
        self.assertEqual(selected.status_code, 200, selected.text)
        project_workflow_id = selected.json()["id"]

        project_workflows = self.client.get(f"/api/projects/{project_id}/workflows")
        self.assertEqual(project_workflows.status_code, 200, project_workflows.text)
        self.assertEqual(project_workflows.json()[0]["id"], project_workflow_id)

        with patch("workbench.remote_workflows.RemoteWorkflowClient.run_workflow", return_value={"prompt_id": "project-prompt"}):
            project_run = self.client.post(
                f"/api/projects/{project_id}/workflows/{project_workflow_id}/runs",
                json={"input_values": {"prompt": "run"}},
            )
        self.assertEqual(project_run.status_code, 200, project_run.text)
        run_id = project_run.json()["id"]

        with patch(
            "workbench.remote_workflows.RemoteWorkflowClient.get_result",
            return_value={
                "prompt_id": "project-prompt",
                "pending": False,
                "results": [{"type": "image", "filename": "out.png", "download_url": "https://example.com/out.png"}],
            },
        ), patch(
            "workbench.remote_workflows.RemoteWorkflowClient.download_file",
            return_value=(b"out", "image/png"),
            create=True,
        ):
            refreshed = self.client.post(f"/api/projects/{project_id}/remote-runs/{run_id}/refresh")
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(refreshed.json()["status"], "succeeded")

        history = self.client.get(f"/api/projects/{project_id}/history")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()[0]["type"], "remote_workflow")

    def test_legacy_numeric_project_urls_return_controlled_errors_instead_of_500(self):
        for path in ["/api/projects/1", "/api/projects/1/assets", "/api/projects/1/history"]:
            response = self.client.get(path)
            self.assertNotEqual(response.status_code, 500, response.text)
            self.assertIn(response.status_code, {403, 404})


if __name__ == "__main__":
    unittest.main()
