import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from workbench.api import create_app
from workbench.auth import CurrentUser, get_current_user
from workbench.config import WorkbenchSettings


class RemoteWorkflowApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root_dir = Path(self.tempdir.name) / "root"
        root_dir.mkdir()
        settings = WorkbenchSettings(
            root_dir=root_dir,
            db_path=root_dir / "workbench.sqlite",
            comfyui_url="http://127.0.0.1:8188",
            default_user="tester",
            default_role="admin",
            jwt_secret="test-secret",
            jwt_expiry_hours=24,
            invite_token_bytes=32,
            invite_expiry_days=7,
            liveblocks_secret_key=None,
            zealman_base_url="https://zealman.example.com",
            zealman_token="secret-token",
        )
        app = create_app(settings)
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=1, username="tester", role="admin")
        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_list_remote_workflows_returns_normalized_payload(self):
        workflows = [
            {
                "id": "wf-1",
                "name": "Portrait Workflow",
                "run_count": 12,
                "last_prompt_id": "prompt-1",
            }
        ]

        with patch("workbench.remote_workflows.RemoteWorkflowClient.list_workflows", return_value=workflows):
            response = self.client.get("/api/remote-workflows", headers={"Authorization": "Bearer demo"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"workflows": workflows})

    def test_run_remote_workflow_and_poll_result(self):
        with patch("workbench.remote_workflows.RemoteWorkflowClient.run_workflow", return_value={"prompt_id": "prompt-123"}), patch(
            "workbench.remote_workflows.RemoteWorkflowClient.get_result",
            return_value={
                "prompt_id": "prompt-123",
                "pending": False,
                "results": [
                    {
                        "type": "image",
                        "url": "/output/result.png",
                        "download_url": "https://zealman.example.com/output/result.png",
                    }
                ],
            },
        ):
            run_response = self.client.post(
                "/api/remote-workflows/wf-1/run",
                headers={"Authorization": "Bearer demo"},
                json={"input_values": {"12:prompt": "hello world"}},
            )
            result_response = self.client.get(
                "/api/remote-workflows/runs/prompt-123",
                headers={"Authorization": "Bearer demo"},
            )

        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run_response.json()["prompt_id"], "prompt-123")
        self.assertEqual(result_response.status_code, 200)
        self.assertFalse(result_response.json()["pending"])
        self.assertEqual(
            result_response.json()["results"][0]["download_url"],
            "https://zealman.example.com/output/result.png",
        )


if __name__ == "__main__":
    unittest.main()
