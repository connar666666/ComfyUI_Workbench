import io
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from workbench.api import create_app
from workbench.auth import CurrentUser, get_current_user
from workbench.config import WorkbenchSettings
from workbench.repositories import WorkbenchRepository


class FolderApiTests(unittest.TestCase):
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

    def tearDown(self):
        self.tempdir.cleanup()

    def test_list_folders_empty(self):
        response = self.client.get("/api/folders")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])

    def test_create_folder_happy_path(self):
        response = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "Reference Frames"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        folder = response.json()
        self.assertEqual(folder["name"], "Reference Frames")
        self.assertEqual(folder["scope"], "assets")
        self.assertEqual(folder["parent_id"], None)
        self.assertEqual(folder["asset_count"], 0)
        self.assertIn("id", folder)

    def test_list_folders_returns_created(self):
        self.client.post("/api/folders", json={"scope": "assets", "name": "Alpha"})
        self.client.post("/api/folders", json={"scope": "assets", "name": "beta"})
        response = self.client.get("/api/folders")
        self.assertEqual(response.status_code, 200, response.text)
        names = [item["name"] for item in response.json()]
        self.assertEqual(names, ["Alpha", "beta"])

    def test_unique_name_conflict_returns_409(self):
        self.client.post("/api/folders", json={"scope": "assets", "name": "Same"})
        response = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "Same"},
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["error"], "conflict")

    def test_unique_name_can_reuse_across_scopes(self):
        self.client.post("/api/folders", json={"scope": "assets", "name": "Shared"})
        response = self.client.post(
            "/api/folders",
            json={"scope": "videos", "name": "Shared"},
        )
        self.assertEqual(response.status_code, 200, response.text)

    def test_rename_folder_updates_name(self):
        created = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "Old"},
        ).json()
        response = self.client.patch(
            f"/api/folders/{created['id']}",
            json={"name": "New"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "New")

    def test_rename_to_duplicate_name_returns_409(self):
        self.client.post("/api/folders", json={"scope": "assets", "name": "First"})
        second = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "Second"},
        ).json()
        response = self.client.patch(
            f"/api/folders/{second['id']}",
            json={"name": "First"},
        )
        self.assertEqual(response.status_code, 409, response.text)

    def test_rename_missing_folder_returns_404(self):
        response = self.client.patch(
            "/api/folders/9999",
            json={"name": "Anything"},
        )
        self.assertEqual(response.status_code, 404, response.text)

    def test_delete_empty_folder_succeeds(self):
        created = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "Disposable"},
        ).json()
        response = self.client.delete(f"/api/folders/{created['id']}")
        self.assertEqual(response.status_code, 200, response.text)
        listing = self.client.get("/api/folders").json()
        self.assertEqual(listing, [])

    def test_delete_folder_with_asset_returns_409(self):
        folder = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "Used"},
        ).json()
        self.client.post(
            "/api/assets",
            data={"kind": "image", "folder_id": str(folder["id"])},
            files={"file": ("pixel.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
        )
        response = self.client.delete(f"/api/folders/{folder['id']}")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("asset", response.json()["message"])

    def test_delete_folder_with_child_returns_409(self):
        parent = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "Parent"},
        ).json()
        self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "Child", "parent_id": parent["id"]},
        )
        response = self.client.delete(f"/api/folders/{parent['id']}")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("sub-folder", response.json()["message"])

    def test_empty_name_rejected(self):
        response = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "   "},
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_oversize_name_rejected(self):
        response = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "x" * 200},
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_invalid_scope_rejected(self):
        response = self.client.post(
            "/api/folders",
            json={"scope": "bogus", "name": "Whatever"},
        )
        self.assertEqual(response.status_code, 400, response.text)

    def test_folder_list_includes_asset_count(self):
        folder = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "Counted"},
        ).json()
        self.client.post(
            "/api/assets",
            data={"kind": "image", "folder_id": str(folder["id"])},
            files={"file": ("a.png", io.BytesIO(b"x"), "image/png")},
        )
        self.client.post(
            "/api/assets",
            data={"kind": "image", "folder_id": str(folder["id"])},
            files={"file": ("b.png", io.BytesIO(b"y"), "image/png")},
        )
        response = self.client.get("/api/folders").json()
        self.assertEqual(response[0]["asset_count"], 2)

    def test_list_assets_supports_folder_filter(self):
        a = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "A"},
        ).json()
        b = self.client.post(
            "/api/folders",
            json={"scope": "assets", "name": "B"},
        ).json()
        for folder_id, name in [(a["id"], "in-a.png"), (b["id"], "in-b.png"), (None, "loose.png")]:
            data = {"kind": "image"}
            if folder_id is not None:
                data["folder_id"] = str(folder_id)
            self.client.post(
                "/api/assets",
                data=data,
                files={"file": (name, io.BytesIO(b"x"), "image/png")},
            )

        listed = self.client.get(f"/api/assets?folder_id={a['id']}").json()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["original_filename"], "in-a.png")
        self.assertEqual(listed[0]["folder_id"], a["id"])

        unfiltered = self.client.get("/api/assets").json()
        self.assertEqual(len(unfiltered), 3)


if __name__ == "__main__":
    unittest.main()