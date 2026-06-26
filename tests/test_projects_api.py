import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from workbench.api import create_app
from workbench.auth import CurrentUser, get_current_user
from workbench.config import WorkbenchSettings
from workbench.repositories import WorkbenchRepository


class ProjectApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root_dir = Path(self.tempdir.name) / "root"
        root_dir.mkdir()
        self.settings = WorkbenchSettings(
            root_dir=root_dir,
            db_path=root_dir / "workbench.sqlite",
            comfyui_url="http://127.0.0.1:8188",
            default_user="owner",
            default_role="admin",
            jwt_secret="test-secret",
            jwt_expiry_hours=24,
            invite_token_bytes=32,
            invite_expiry_days=7,
            liveblocks_secret_key=None,
            zealman_base_url="https://zealman.example.com",
            zealman_token="secret-token",
        )
        self.app = create_app(self.settings)
        self.current_user = CurrentUser(id=1, username="owner", role="admin")
        self.app.dependency_overrides[get_current_user] = lambda: self.current_user
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.repo = WorkbenchRepository(self.settings.db_path)
        self.viewer = self.repo.create_user(username="viewer", display_name="Viewer", role="member")

    def tearDown(self):
        self.tempdir.cleanup()

    def as_user(self, user_id: int, username: str, role: str = "member") -> None:
        self.current_user = CurrentUser(id=user_id, username=username, role=role)

    def create_project(self, name: str = "Campaign") -> dict:
        response = self.client.post(
            "/api/projects",
            json={"name": name, "description": "Launch work", "members": []},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_create_project_adds_creator_as_owner(self):
        project = self.create_project()

        self.assertEqual(project["name"], "Campaign")
        self.assertEqual(project["current_user_role"], "owner")
        self.assertEqual(project["members"][0]["role"], "owner")
        self.assertIsInstance(project["members"][0]["user_id"], str)

    def test_viewer_can_read_but_cannot_upload_project_assets(self):
        project = self.create_project()
        add_member = self.client.put(
            f"/api/projects/{project['id']}/members/{self.viewer['id']}",
            json={"role": "viewer"},
        )
        self.assertEqual(add_member.status_code, 200, add_member.text)

        self.as_user(self.viewer["id"], "viewer")

        read_response = self.client.get(f"/api/projects/{project['id']}")
        self.assertEqual(read_response.status_code, 200, read_response.text)

        upload_response = self.client.post(
            f"/api/projects/{project['id']}/assets",
            data={"kind": "image"},
            files={"file": ("sample.png", io.BytesIO(b"fake"), "image/png")},
        )
        self.assertEqual(upload_response.status_code, 403)

    def test_project_assets_are_private_to_project(self):
        project_a = self.create_project("Project A")
        project_b = self.create_project("Project B")

        upload_response = self.client.post(
            f"/api/projects/{project_a['id']}/assets",
            data={"kind": "image"},
            files={"file": ("sample.png", io.BytesIO(b"project-a"), "image/png")},
        )
        self.assertEqual(upload_response.status_code, 200, upload_response.text)

        assets_a = self.client.get(f"/api/projects/{project_a['id']}/assets")
        assets_b = self.client.get(f"/api/projects/{project_b['id']}/assets")

        self.assertEqual(len(assets_a.json()), 1)
        self.assertEqual(assets_a.json()[0]["project_id"], project_a["id"])
        self.assertEqual(assets_b.json(), [])

    def test_project_folders_are_private_to_project(self):
        project_a = self.create_project("Project A")
        project_b = self.create_project("Project B")

        folder_a = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "References", "project_id": project_a["id"]},
        )
        self.assertEqual(folder_a.status_code, 200, folder_a.text)
        folder_b = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "References", "project_id": project_b["id"]},
        )
        self.assertEqual(folder_b.status_code, 200, folder_b.text)

        folders_a = self.client.get(f"/api/folders?project_id={project_a['id']}")
        folders_b = self.client.get(f"/api/folders?project_id={project_b['id']}")

        self.assertEqual([folder["id"] for folder in folders_a.json()], [folder_a.json()["id"]])
        self.assertEqual([folder["id"] for folder in folders_b.json()], [folder_b.json()["id"]])

    def test_project_workflow_run_refreshes_result_and_appears_in_history(self):
        project = self.create_project()

        add_workflow = self.client.post(
            f"/api/projects/{project['id']}/workflows",
            json={"workflow_id": "wf-portrait", "display_name": "Portrait", "defaults": {"12:prompt": "hello"}},
        )
        self.assertEqual(add_workflow.status_code, 200, add_workflow.text)
        project_workflow_id = add_workflow.json()["id"]

        with patch("workbench.remote_workflows.RemoteWorkflowClient.run_workflow", return_value={"prompt_id": "prompt-1"}):
            run_response = self.client.post(
                f"/api/projects/{project['id']}/workflows/{project_workflow_id}/runs",
                json={"input_values": {"12:prompt": "new prompt"}},
            )
        self.assertEqual(run_response.status_code, 200, run_response.text)
        run_id = run_response.json()["id"]
        self.assertEqual(run_response.json()["status"], "running")

        with patch(
            "workbench.remote_workflows.RemoteWorkflowClient.get_result",
            return_value={
                "prompt_id": "prompt-1",
                "pending": False,
                "results": [
                    {
                        "type": "image",
                        "filename": "output.png",
                        "download_url": "https://zealman.example.com/output.png",
                    }
                ],
            },
        ), patch(
            "workbench.remote_workflows.RemoteWorkflowClient.download_file",
            return_value=(b"image-bytes", "image/png"),
            create=True,
        ):
            refresh_response = self.client.post(f"/api/projects/{project['id']}/remote-runs/{run_id}/refresh")

        self.assertEqual(refresh_response.status_code, 200, refresh_response.text)
        self.assertEqual(refresh_response.json()["status"], "succeeded")
        self.assertEqual(len(refresh_response.json()["saved_asset_ids"]), 1)

        history_response = self.client.get(f"/api/projects/{project['id']}/history")
        self.assertEqual(history_response.status_code, 200, history_response.text)
        self.assertEqual(history_response.json()[0]["type"], "remote_workflow")
        self.assertEqual(history_response.json()[0]["status"], "succeeded")
        self.assertEqual(history_response.json()[0]["title"], "Portrait")
        self.assertEqual(len(history_response.json()[0]["result_asset_ids"]), 1)

        assets_response = self.client.get(f"/api/projects/{project['id']}/assets")
        self.assertEqual(assets_response.status_code, 200, assets_response.text)
        self.assertEqual(assets_response.json()[0]["original_filename"], "output.png")


if __name__ == "__main__":
    unittest.main()
