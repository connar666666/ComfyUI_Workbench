import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from workbench.api import create_app
from workbench.config import WorkbenchSettings


class QueueApiTests(unittest.TestCase):
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
        )
        self.client = TestClient(create_app(settings), raise_server_exceptions=False)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_queue_upstream_failures_return_readable_service_error(self):
        with patch("workbench.comfyui_queue.ComfyUIQueueClient.__init__", return_value=None), patch(
            "workbench.comfyui_queue.ComfyUIQueueClient.fetch_queue",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            response = self.client.get("/api/comfyui/queue")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["message"], "ComfyUI queue is unavailable")


if __name__ == "__main__":
    unittest.main()
