from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from workbench.api import create_app
from workbench.auth import CurrentUser, create_access_token, get_current_user
from workbench.config import WorkbenchSettings
from workbench.db import initialize_db
from workbench.repositories import WorkbenchRepository


def _settings(root_dir: Path) -> WorkbenchSettings:
    return WorkbenchSettings(
        root_dir=root_dir,
        db_path=root_dir / "workbench.sqlite",
        comfyui_url="http://127.0.0.1:8188",
        zealman_base_url="https://zealman.example.com",
        zealman_token="secret-token",
        default_user="owner",
        default_role="admin",
        jwt_secret="test-secret",
        jwt_expiry_hours=24,
        invite_token_bytes=16,
        invite_expiry_days=7,
        liveblocks_secret_key="liveblocks-secret",
    )


@pytest.fixture
def env(tmp_path: Path):
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    settings = _settings(root_dir)
    app = create_app(settings)
    repo = WorkbenchRepository(settings.db_path)
    user = repo.get_user_by_username("owner")
    current_user = CurrentUser(id=user["id"], username="owner", role="admin")
    app.dependency_overrides[get_current_user] = lambda: current_user
    client = TestClient(app, raise_server_exceptions=False)
    yield app, client, repo, current_user


@pytest.fixture
def authed_client(env):
    _app, client, _repo, _user = env
    return client


@pytest.fixture
def auth_headers(env):
    _app, _client, repo, user = env
    token = create_access_token(user["id"], "owner", "admin")
    return {"Authorization": f"Bearer {token}"}


class TestHealthEndpoint:
    def test_returns_ok(self, authed_client: TestClient):
        response = authed_client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestUsersEndpoint:
    def test_lists_users(self, authed_client: TestClient):
        response = authed_client.get("/api/users")
        assert response.status_code == 200
        usernames = [u["username"] for u in response.json()]
        assert "owner" in usernames


class TestLiveblocksAuth:
    def test_requires_canvas_room_prefix(self, env):
        _app, client, _repo, _user = env
        response = client.post("/api/liveblocks-auth", json={"room": "not-a-canvas"})
        assert response.status_code == 403

    def test_requires_configured_secret(self, tmp_path: Path):
        # Build a fresh app with liveblocks_secret_key=None.
        root_dir = tmp_path / "root"
        root_dir.mkdir()
        settings = _settings(root_dir)
        settings = WorkbenchSettings(**{**settings.__dict__, "liveblocks_secret_key": None})
        app = create_app(settings)
        repo = WorkbenchRepository(settings.db_path)
        user = repo.get_user_by_username("owner")
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user["id"], username="owner", role="admin")
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/api/liveblocks-auth", json={"room": "canvas:foo"})
        assert response.status_code == 400
        assert response.json()["message"] == "LIVEBLOCKS_SECRET_KEY is not configured"

    def test_forwards_user_id_to_liveblocks(self, env):
        _app, client, repo, _user = env

        class _Resp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"token": "lb-token"}

        with patch("workbench.api.httpx.post", return_value=_Resp()) as mock_post:
            response = client.post("/api/liveblocks-auth", json={"room": "canvas:room-1"})

        assert response.status_code == 200
        assert response.json() == {"token": "lb-token"}
        body = mock_post.call_args.kwargs["json"]
        assert body["userId"] == repo.get_user_by_username("owner")["id"]
        assert body["permissions"] == {"canvas:room-1": ["room:write"]}

    def test_returns_validation_error_on_unauthorized(self, env):
        _app, client, _repo, _user = env

        class _Resp:
            status_code = 401
            text = "Unauthorized"

            def raise_for_status(self):
                err = httpx.HTTPStatusError("unauthorized", request=httpx.Request("POST", "https://x"), response=httpx.Response(401))
                raise err

        with patch("workbench.api.httpx.post", return_value=_Resp()):
            response = client.post("/api/liveblocks-auth", json={"room": "canvas:foo"})
        assert response.status_code == 400
        assert "Liveblocks" in response.json()["message"]


class TestResolveUsers:
    def test_returns_known_and_fallback_names(self, env):
        _app, client, _repo, _user = env
        # Use the admin's UUID plus a fake one.
        owner_id = _repo.get_user_by_username("owner")["id"]
        response = client.post(
            "/api/liveblocks/resolve-users",
            json={"userIds": [owner_id, "11111111-1111-1111-1111-111111111111"]},
        )
        assert response.status_code == 200
        users = response.json()
        assert users[0]["id"] == owner_id
        assert users[0]["name"] == "owner"
        # The unknown user should fall back to user#<id>.
        assert users[1]["name"] == "user#11111111-1111-1111-1111-111111111111"


class TestComfyUIQueueEndpoint:
    def test_returns_normalized_queue(self, env):
        _app, client, _repo, _user = env
        normalized = {
            "running": [{"prompt_id": "running-prompt", "queue_position": 0, "raw": ["running-prompt", {}]}],
            "pending": [
                {"prompt_id": "pending-1", "queue_position": 0, "raw": ["pending-1", {}]},
                {"prompt_id": "pending-2", "queue_position": 1, "raw": ["pending-2", {}]},
            ],
        }
        with patch(
            "workbench.comfyui_queue.ComfyUIQueueClient.__init__",
            return_value=None,
        ), patch(
            "workbench.comfyui_queue.ComfyUIQueueClient.fetch_queue",
            return_value=normalized,
        ):
            response = client.get("/api/comfyui/queue")

        assert response.status_code == 200
        body = response.json()
        assert body["running"][0]["prompt_id"] == "running-prompt"
        assert len(body["pending"]) == 2

    def test_returns_503_on_invalid_json(self, env):
        _app, client, _repo, _user = env
        with patch(
            "workbench.comfyui_queue.ComfyUIQueueClient.__init__",
            return_value=None,
        ), patch(
            "workbench.comfyui_queue.ComfyUIQueueClient.fetch_queue",
            side_effect=ValueError("not json"),
        ):
            response = client.get("/api/comfyui/queue")
        assert response.status_code == 503
        assert "invalid response" in response.json()["message"]


class TestFileStreaming:
    def test_stream_asset_returns_bytes(self, env):
        _app, client, repo, _user = env
        # Upload an asset via the API to populate the database and disk.
        upload = client.post(
            "/api/assets",
            data={"kind": "image"},
            files={"file": ("sample.png", io.BytesIO(b"image-bytes"), "image/png")},
        )
        assert upload.status_code == 200, upload.text
        asset_id = upload.json()["id"]

        response = client.get(f"/files/assets/{asset_id}")
        assert response.status_code == 200
        assert response.content == b"image-bytes"

    def test_stream_asset_missing_returns_404(self, env):
        _app, client, _repo, _user = env
        response = client.get("/files/assets/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestAuthDependency:
    def test_missing_auth_returns_403(self, env):
        _app, client, _repo, _user = env
        # Bypass the dependency override by hitting an endpoint directly via a fresh client.
        fresh_app = _app
        fresh_app.dependency_overrides.pop(get_current_user, None)

        # TestClient still works after override removal; should now hit the real dependency.
        response = client.get("/api/users", headers={})
        assert response.status_code == 403
        assert "Missing or invalid" in response.json()["message"]

    def test_invalid_token_returns_403(self, env):
        _app, client, _repo, _user = env
        _app.dependency_overrides.pop(get_current_user, None)
        response = client.get("/api/users", headers={"Authorization": "Bearer garbage"})
        assert response.status_code == 403


class TestHealthAndCors:
    def test_cors_headers_allow_origin(self, env):
        _app, client, _repo, _user = env
        response = client.get("/api/health", headers={"Origin": "http://example.com"})
        assert response.status_code == 200
        # CORS is configured with allow_origins=["*"]; FastAPI echoes the origin.
        assert response.headers.get("access-control-allow-origin") == "http://example.com"


class TestJobCreateEndpoint:
    def test_create_and_list_jobs(self, env):
        _app, client, _repo, _user = env
        response = client.post(
            "/api/jobs",
            json={"prompt": "hello", "duration_sec": 4, "resolution": "720x1280"},
        )
        assert response.status_code == 200, response.text
        job = response.json()
        assert job["status"] == "queued"
        assert job["prompt"] == "hello"

        listed = client.get("/api/jobs")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

    def test_create_job_validation_error(self, env):
        _app, client, _repo, _user = env
        response = client.post(
            "/api/jobs",
            json={"prompt": "", "duration_sec": 4, "resolution": "720x1280"},
        )
        assert response.status_code == 400
        assert "prompt" in response.json()["message"]

    def test_create_job_bad_resolution(self, env):
        _app, client, _repo, _user = env
        response = client.post(
            "/api/jobs",
            json={"prompt": "hi", "duration_sec": 4, "resolution": "640x480"},
        )
        assert response.status_code == 400


class TestCanvasVersionsEndpoint:
    def test_list_versions_for_canvas(self, env):
        _app, client, repo, user = env
        version = repo.create_node_version(
            canvas_id="canvas-1", node_id="node-1", generation_job_id=None,
            output_video_id=None, prompt="p", input_asset_ids=[],
            params={"k": "v"}, snapshot={"id": "node-1"}, status="succeeded",
            created_by=user.id,
        )
        all_versions = client.get("/api/canvas/canvas-1/versions")
        node_versions = client.get("/api/canvas/canvas-1/nodes/node-1/versions")

        assert all_versions.status_code == 200
        assert len(all_versions.json()) == 1
        assert node_versions.status_code == 200
        assert node_versions.json()[0]["id"] == version["id"]


class TestVideosEndpoint:
    def test_list_videos_returns_empty(self, env):
        _app, client, _repo, _user = env
        response = client.get("/api/videos")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_videos_after_creation(self, env):
        _app, client, repo, user = env
        video = repo.create_video(
            source_job_id=None, created_by=user.id, title="x.mp4",
            storage_key="outputs/videos/x.mp4", mime_type="video/mp4", size_bytes=4,
        )
        response = client.get("/api/videos")
        assert response.status_code == 200
        assert any(v["id"] == video["id"] for v in response.json())


class TestAuthRouterEndpoints:
    def test_register_validation_short_username(self, env):
        _app, client, _repo, _user = env
        _app.dependency_overrides.pop(get_current_user, None)
        response = client.post("/api/auth/register", json={"username": "x", "password": "pass1234"})
        assert response.status_code == 400

    def test_register_validation_short_password(self, env):
        _app, client, _repo, _user = env
        _app.dependency_overrides.pop(get_current_user, None)
        response = client.post("/api/auth/register", json={"username": "alice", "password": "x"})
        assert response.status_code == 400

    def test_login_invalid_returns_403(self, env):
        _app, client, _repo, _user = env
        _app.dependency_overrides.pop(get_current_user, None)
        response = client.post("/api/auth/login", json={"username": "nobody", "password": "x"})
        assert response.status_code == 403

    def test_refresh_with_invalid_token(self, env):
        _app, client, _repo, _user = env
        _app.dependency_overrides.pop(get_current_user, None)
        response = client.post("/api/auth/refresh", json={"refresh_token": "garbage"})
        assert response.status_code == 403


class TestOpenApi:
    def test_openapi_schema_includes_key_endpoints(self, env):
        _app, _client, _repo, _user = env
        schema = _app.openapi()
        paths = schema["paths"].keys()
        for expected in [
            "/api/health",
            "/api/users",
            "/api/assets",
            "/api/folders",
            "/api/jobs",
            "/api/projects",
            "/api/videos",
            "/api/events",
        ]:
            assert expected in paths, f"missing route {expected}"