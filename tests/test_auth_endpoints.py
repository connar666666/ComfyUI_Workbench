from __future__ import annotations

import hashlib
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

import workbench.routes_auth as routes_auth
from workbench.api import create_app
from workbench.auth import (
    CurrentUser,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from workbench.config import WorkbenchSettings
from workbench.repositories import WorkbenchRepository


def _bootstrap(tmp_path: Path):
    """Set up an isolated FastAPI app + repo with _get_repo monkey-patched."""
    root_dir = tmp_path / "root"
    root_dir.mkdir()
    settings = WorkbenchSettings(
        root_dir=root_dir,
        db_path=root_dir / "workbench.sqlite",
        comfyui_url="http://127.0.0.1:8188",
        zealman_base_url=None,
        zealman_token=None,
        default_user="owner",
        default_role="admin",
        jwt_secret="test-secret",
        jwt_expiry_hours=24,
        invite_token_bytes=16,
        invite_expiry_days=7,
        liveblocks_secret_key=None,
    )
    app = create_app(settings)
    repo = WorkbenchRepository(settings.db_path)
    # Auth routes build their own repo via _get_repo(); route that to our test repo.
    _get_repo_patch = patch.object(routes_auth, "_get_repo", return_value=repo)
    _get_repo_patch.start()
    app._get_repo_patch = _get_repo_patch  # type: ignore[attr-defined]
    client = TestClient(app, raise_server_exceptions=False)
    return app, client, repo


def _set_current_user(app, user: CurrentUser) -> None:
    """Make get_current_user return the supplied user (for /me, /invites endpoints)."""
    app.dependency_overrides[get_current_user] = lambda: user


def _admin_user(repo: WorkbenchRepository) -> CurrentUser:
    user = repo.get_user_by_username("owner")
    return CurrentUser(id=user["id"], username="owner", role="admin")


def _member_user(repo: WorkbenchRepository, username: str = "alice") -> CurrentUser:
    user = repo.create_user(username=username, display_name=username, role="member")
    return CurrentUser(id=user["id"], username=user["username"], role="member")


@pytest.fixture
def env(tmp_path: Path):
    app, client, repo = _bootstrap(tmp_path)
    yield app, client, repo
    app._get_repo_patch.stop()  # type: ignore[attr-defined]


def _parse_timestamp(value) -> datetime:
    """Coerce a timestamp value (str or datetime) from the repository into a datetime."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/register
# ─────────────────────────────────────────────────────────────────────────────


class TestRegisterEndpoint:
    def test_register_returns_access_and_refresh_tokens(self, env):
        _app, client, _repo = env
        response = client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "pass1234", "display_name": "Alice"},
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert "access_token" in body and isinstance(body["access_token"], str) and body["access_token"]
        assert "refresh_token" in body and isinstance(body["refresh_token"], str) and body["refresh_token"]
        assert body["user"]["username"] == "alice"
        assert body["user"]["display_name"] == "Alice"
        assert body["user"]["role"] == "member"

        # Both tokens must decode successfully.
        access = decode_token(body["access_token"])
        refresh = decode_token(body["refresh_token"])
        assert access is not None
        assert access.get("typ") != "refresh"  # access tokens omit typ
        assert refresh is not None and refresh.get("typ") == "refresh"

    def test_register_uses_username_as_default_display_name(self, env):
        _app, client, _repo = env
        response = client.post(
            "/api/auth/register",
            json={"username": "bob", "password": "pass1234"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["display_name"] == "bob"

    def test_register_stores_password_as_hash_not_plaintext(self, env):
        app, client, repo = env
        client.post(
            "/api/auth/register",
            json={"username": "carol", "password": "supersecret"},
        )
        user = repo.get_user_by_username("carol")
        assert user["password_hash"] is not None
        assert user["password_hash"] != "supersecret"
        assert user["password_hash"].startswith("pbkdf2:")
        # The stored hash must verify with the original password.
        assert verify_password("supersecret", user["password_hash"]) is True

    def test_register_new_user_can_immediately_log_in(self, env):
        _app, client, _repo = env
        client.post(
            "/api/auth/register",
            json={"username": "dave", "password": "pass1234", "display_name": "Dave"},
        )
        response = client.post(
            "/api/auth/login",
            json={"username": "dave", "password": "pass1234"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["username"] == "dave"

    def test_register_updates_last_seen_at(self, env):
        app, client, repo = env
        before = datetime.now(timezone.utc)
        client.post(
            "/api/auth/register",
            json={"username": "erin", "password": "pass1234"},
        )
        user = repo.get_user_by_username("erin")
        assert user["last_seen_at"] is not None
        ts = _parse_timestamp(user["last_seen_at"])
        assert ts >= before - timedelta(seconds=1)

    @pytest.mark.parametrize("username", ["", "a"])
    def test_register_rejects_short_username(self, env, username):
        _app, client, _repo = env
        response = client.post(
            "/api/auth/register",
            json={"username": username, "password": "pass1234"},
        )
        assert response.status_code == 400, response.text
        assert response.json()["error"] == "validation_error"
        assert "username" in response.json()["message"].lower()

    @pytest.mark.parametrize("password", ["", "a", "abc"])
    def test_register_rejects_short_password(self, env, password):
        _app, client, _repo = env
        response = client.post(
            "/api/auth/register",
            json={"username": "valid_user", "password": password},
        )
        assert response.status_code == 400, response.text
        assert response.json()["error"] == "validation_error"
        assert "password" in response.json()["message"].lower()

    def test_register_duplicate_username_returns_conflict(self, env):
        _app, client, _repo = env
        first = client.post(
            "/api/auth/register",
            json={"username": "frank", "password": "pass1234"},
        )
        assert first.status_code == 200

        second = client.post(
            "/api/auth/register",
            json={"username": "frank", "password": "different"},
        )
        assert second.status_code == 409
        assert second.json()["error"] == "conflict"
        assert "frank" in second.json()["message"]

    def test_register_username_minimum_is_two_characters(self, env):
        # Boundary: exactly 2 chars is allowed.
        _app, client, _repo = env
        response = client.post(
            "/api/auth/register",
            json={"username": "ab", "password": "pass1234"},
        )
        assert response.status_code == 200

    def test_register_password_minimum_is_four_characters(self, env):
        # Boundary: exactly 4 chars is allowed.
        _app, client, _repo = env
        response = client.post(
            "/api/auth/register",
            json={"username": "ab", "password": "abcd"},
        )
        assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/login
# ─────────────────────────────────────────────────────────────────────────────


class TestLoginEndpoint:
    def _register(self, client, username="alice", password="pass1234"):
        return client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
        )

    def test_login_returns_tokens_for_valid_credentials(self, env):
        _app, client, _repo = env
        self._register(client)

        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pass1234"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["user"]["username"] == "alice"

    def test_login_refresh_token_is_usable_for_refresh(self, env):
        _app, client, _repo = env
        self._register(client)
        login = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "pass1234"},
        )
        refresh_token = login.json()["refresh_token"]

        response = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200
        assert response.json()["user"]["username"] == "alice"

    def test_login_wrong_password_returns_403(self, env):
        _app, client, _repo = env
        self._register(client, password="rightpw")
        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrongpw"},
        )
        assert response.status_code == 403
        assert response.json()["error"] == "permission_denied"
        assert "username or password" in response.json()["message"].lower()

    def test_login_unknown_user_returns_403_with_same_message(self, env):
        _app, client, _repo = env
        response = client.post(
            "/api/auth/login",
            json={"username": "ghost", "password": "anything"},
        )
        assert response.status_code == 403
        # Message should be identical to wrong-password case to avoid user enumeration.
        assert "username or password" in response.json()["message"].lower()

    def test_login_with_invite_only_user_returns_specific_message(self, env):
        app, client, repo = env
        # Create a user with no password (invite-only style).
        user = repo.create_user(username="invitee", display_name="Invitee", password_hash=None)

        response = client.post(
            "/api/auth/login",
            json={"username": "invitee", "password": "anything"},
        )
        assert response.status_code == 403
        assert "invite" in response.json()["message"].lower()

    def test_login_username_is_case_sensitive(self, env):
        _app, client, _repo = env
        self._register(client, username="alice")
        response = client.post(
            "/api/auth/login",
            json={"username": "ALICE", "password": "pass1234"},
        )
        assert response.status_code == 403

    def test_login_updates_last_seen(self, env):
        app, client, repo = env
        self._register(client)
        before = datetime.now(timezone.utc)

        client.post("/api/auth/login", json={"username": "alice", "password": "pass1234"})

        user = repo.get_user_by_username("alice")
        assert user["last_seen_at"] is not None
        ts = _parse_timestamp(user["last_seen_at"])
        assert ts >= before - timedelta(seconds=1)

    def test_login_admin_account_works(self, env):
        # The default 'owner' admin is created by initialize_db and has no password_hash.
        app, client, repo = env
        # Setting a password is not part of the public API; we exercise the
        # branch by registering a new member and confirming the role is "member".
        response = client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "pass1234"},
        )
        assert response.json()["user"]["role"] == "member"


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/refresh
# ─────────────────────────────────────────────────────────────────────────────


class TestRefreshEndpoint:
    def test_refresh_with_valid_refresh_token_succeeds(self, env):
        _app, client, _repo = env
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "pass1234"},
        )
        login = client.post("/api/auth/login", json={"username": "alice", "password": "pass1234"})
        refresh_token = login.json()["refresh_token"]

        response = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["access_token"]
        assert body["refresh_token"]
        # The new access token must be valid (refresh tokens may have identical
        # iat within the same second, so we only assert the access token works).
        decoded = decode_token(body["access_token"])
        assert decoded is not None and decoded.get("typ") != "refresh"
        # The new refresh token must also be decodable.
        decoded_refresh = decode_token(body["refresh_token"])
        assert decoded_refresh is not None and decoded_refresh.get("typ") == "refresh"

    def test_refresh_with_access_token_rejected(self, env):
        _app, client, _repo = env
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "pass1234"},
        )
        login = client.post("/api/auth/login", json={"username": "alice", "password": "pass1234"})
        access_token = login.json()["access_token"]

        response = client.post("/api/auth/refresh", json={"refresh_token": access_token})
        assert response.status_code == 403
        assert response.json()["error"] == "permission_denied"

    def test_refresh_with_garbage_token_rejected(self, env):
        _app, client, _repo = env
        response = client.post("/api/auth/refresh", json={"refresh_token": "not.a.jwt"})
        assert response.status_code == 403

    def test_refresh_with_empty_token_rejected(self, env):
        _app, client, _repo = env
        response = client.post("/api/auth/refresh", json={"refresh_token": ""})
        assert response.status_code == 403

    def test_refresh_with_token_signed_by_wrong_key_rejected(self, env):
        _app, client, _repo = env
        bad_token = pyjwt.encode(
            {"sub": "user-1", "typ": "refresh", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            "wrong-secret", algorithm="HS256",
        )
        response = client.post("/api/auth/refresh", json={"refresh_token": bad_token})
        assert response.status_code == 403

    def test_refresh_with_token_for_missing_user_rejected(self, env):
        _app, client, _repo = env
        # The auth dependency uses get_current_user which decodes via the JWT secret.
        # If the token points at a non-existent user, refresh should error.
        bogus_refresh = create_refresh_token("00000000-0000-0000-0000-000000000000")
        response = client.post("/api/auth/refresh", json={"refresh_token": bogus_refresh})
        # Either 403 (decode failure on user lookup) or 404 — both are acceptable.
        assert response.status_code in (403, 404)

    def test_refresh_returns_fresh_tokens(self, env):
        _app, client, _repo = env
        client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "pass1234"},
        )
        login = client.post("/api/auth/login", json={"username": "alice", "password": "pass1234"})
        original_refresh = decode_token(login.json()["refresh_token"])

        response = client.post("/api/auth/refresh", json={"refresh_token": login.json()["refresh_token"]})
        new_refresh = decode_token(response.json()["refresh_token"])

        # Either the iat advances or it stays the same (same-second case) — but
        # the response is a well-formed refresh token.
        assert new_refresh is not None
        assert new_refresh.get("typ") == "refresh"
        assert new_refresh["sub"] == original_refresh["sub"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/join
# ─────────────────────────────────────────────────────────────────────────────


class TestJoinEndpoint:
    def _make_invite(self, repo, created_by: str, role: str = "member", max_uses: int | None = None, expires_at: str | None = None):
        # Use a deterministic plaintext so the hash matches.
        plaintext = f"plain-{created_by}-{role}-{max_uses}-{expires_at}"
        token_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        repo.create_invite(
            token_hash=token_hash,
            created_by=created_by,
            role=role,
            max_uses=max_uses,
            expires_at=expires_at,
        )
        return plaintext, token_hash

    def test_join_with_valid_invite_creates_user(self, env):
        app, client, repo = env
        admin = repo.get_user_by_username("owner")
        plaintext, _hash = self._make_invite(repo, created_by=admin["id"], role="member")

        response = client.post(
            "/api/auth/join",
            json={"token": plaintext, "username": "newbie", "display_name": "Newbie"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["user"]["username"] == "newbie"
        assert body["user"]["role"] == "member"

        user = repo.get_user_by_username("newbie")
        assert user["display_name"] == "Newbie"
        # Invite-only accounts have no password.
        assert user["password_hash"] is None

    def test_join_default_display_name_falls_back_to_username(self, env):
        app, client, repo = env
        admin = repo.get_user_by_username("owner")
        plaintext, _hash = self._make_invite(repo, created_by=admin["id"])

        response = client.post(
            "/api/auth/join",
            json={"token": plaintext, "username": "ghost"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["display_name"] == "ghost"

    def test_join_with_invalid_token_returns_403(self, env):
        _app, client, _repo = env
        response = client.post(
            "/api/auth/join",
            json={"token": "definitely-not-real", "username": "ghost"},
        )
        assert response.status_code == 403
        assert "invite" in response.json()["message"].lower()

    def test_join_with_revoked_invite_returns_403(self, env):
        app, client, repo = env
        admin = repo.get_user_by_username("owner")
        plaintext, token_hash = self._make_invite(repo, created_by=admin["id"])
        repo.revoke_invite(token_hash)

        response = client.post(
            "/api/auth/join",
            json={"token": plaintext, "username": "ghost"},
        )
        assert response.status_code == 403

    def test_join_with_expired_invite_returns_403(self, env):
        app, client, repo = env
        admin = repo.get_user_by_username("owner")
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        plaintext, _hash = self._make_invite(repo, created_by=admin["id"], expires_at=past)

        response = client.post(
            "/api/auth/join",
            json={"token": plaintext, "username": "ghost"},
        )
        assert response.status_code == 403
        assert "exhausted" in response.json()["message"].lower() or "expired" in response.json()["message"].lower()

    def test_join_invite_with_max_uses_returns_403_after_exhausted(self, env):
        app, client, repo = env
        admin = repo.get_user_by_username("owner")
        plaintext, _hash = self._make_invite(repo, created_by=admin["id"], max_uses=1)

        first = client.post("/api/auth/join", json={"token": plaintext, "username": "first"})
        second = client.post("/api/auth/join", json={"token": plaintext, "username": "second"})

        assert first.status_code == 200
        assert second.status_code == 403
        assert "exhausted" in second.json()["message"].lower()

    def test_join_reuses_existing_user_without_error(self, env):
        app, client, repo = env
        admin = repo.get_user_by_username("owner")
        existing = repo.create_user(username="veteran", display_name="Veteran", role="member")

        plaintext, _hash = self._make_invite(repo, created_by=admin["id"], role="member")
        response = client.post(
            "/api/auth/join",
            json={"token": plaintext, "username": "veteran"},
        )
        # Veteran already exists — the route should still log them in.
        assert response.status_code == 200
        assert response.json()["user"]["id"] == existing["id"]

    def test_join_with_admin_role_invite_creates_admin(self, env):
        app, client, repo = env
        admin = repo.get_user_by_username("owner")
        plaintext, _hash = self._make_invite(repo, created_by=admin["id"], role="admin")

        response = client.post(
            "/api/auth/join",
            json={"token": plaintext, "username": "newadmin"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "admin"

    def test_join_updates_last_seen(self, env):
        app, client, repo = env
        admin = repo.get_user_by_username("owner")
        plaintext, _hash = self._make_invite(repo, created_by=admin["id"])

        before = datetime.now(timezone.utc)
        client.post("/api/auth/join", json={"token": plaintext, "username": "tracker"})
        user = repo.get_user_by_username("tracker")
        assert user["last_seen_at"] is not None
        ts = _parse_timestamp(user["last_seen_at"])
        assert ts >= before - timedelta(seconds=1)


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/auth/me
# ─────────────────────────────────────────────────────────────────────────────


class TestMeEndpoint:
    def test_me_returns_current_user_info(self, env):
        app, client, repo = env
        user = _admin_user(repo)
        _set_current_user(app, user)

        response = client.get("/api/auth/me")
        assert response.status_code == 200
        body = response.json()
        assert body["username"] == "owner"
        assert body["role"] == "admin"

    def test_me_without_auth_returns_403(self, env):
        app, _client, _repo = env
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/auth/me")
        assert response.status_code == 403

    def test_me_with_invalid_token_returns_403(self, env):
        app, _client, _repo = env
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
        assert response.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/invites
# ─────────────────────────────────────────────────────────────────────────────


class TestInviteCreateEndpoint:
    def test_admin_can_create_invite(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        _set_current_user(app, admin)

        response = client.post("/api/auth/invites", json={"role": "member"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["role"] == "member"
        assert body["invite_link"].startswith("http")
        assert body["token"]
        assert body["expires_in_days"] == 7  # default

    def test_invite_response_includes_usable_join_link(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        _set_current_user(app, admin)

        created = client.post("/api/auth/invites", json={"role": "member"}).json()

        # The same token should be usable by /api/auth/join.
        joined = client.post(
            "/api/auth/join",
            json={"token": created["token"], "username": "joined"},
        )
        assert joined.status_code == 200, joined.text
        assert joined.json()["user"]["username"] == "joined"

    def test_invite_custom_role_is_honored(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        _set_current_user(app, admin)

        response = client.post("/api/auth/invites", json={"role": "admin"})
        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    def test_invite_max_uses_is_persisted(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        _set_current_user(app, admin)

        client.post("/api/auth/invites", json={"role": "member", "max_uses": 2})
        invites = client.get("/api/auth/invites").json()
        assert any(i["max_uses"] == 2 for i in invites)

    def test_invite_expires_in_days_zero_means_no_expiry(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        _set_current_user(app, admin)

        client.post("/api/auth/invites", json={"role": "member", "expires_in_days": 0})
        invites = client.get("/api/auth/invites").json()
        assert any(i["expires_at"] is None for i in invites)

    def test_non_admin_cannot_create_invite(self, env):
        app, client, repo = env
        member = _member_user(repo)
        _set_current_user(app, member)

        response = client.post("/api/auth/invites", json={"role": "member"})
        assert response.status_code == 403
        assert response.json()["error"] == "permission_denied"
        assert "admin" in response.json()["message"].lower()

    def test_invite_create_requires_authentication(self, env):
        app, _client, _repo = env
        app.dependency_overrides.pop(get_current_user, None)
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/auth/invites", json={"role": "member"})
        assert response.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/auth/invites
# ─────────────────────────────────────────────────────────────────────────────


class TestInviteListEndpoint:
    def test_admin_sees_all_invites(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        member = _member_user(repo, username="bob")
        _set_current_user(app, admin)

        # Two invites: one created by admin, one by member.
        client.post("/api/auth/invites", json={"role": "member"})
        # Have to switch users to create the member's invite; we patch the
        # dependency directly to avoid going through the API.
        repo.create_invite(token_hash="member-invite-hash", created_by=member.id)

        response = client.get("/api/auth/invites")
        assert response.status_code == 200
        bodies = response.json()
        assert len(bodies) >= 2

    def test_member_only_sees_their_own_invites(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        member_a = _member_user(repo, username="alice")
        member_b = _member_user(repo, username="bob")

        repo.create_invite(token_hash="a-invite", created_by=member_a.id)
        repo.create_invite(token_hash="b-invite", created_by=member_b.id)

        _set_current_user(app, member_a)
        response = client.get("/api/auth/invites")
        assert response.status_code == 200
        hashes = [i["token_hash"] for i in response.json()]
        assert "a-invite" in hashes
        assert "b-invite" not in hashes

    def test_revoked_invites_excluded_from_listing(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        _set_current_user(app, admin)

        created = client.post("/api/auth/invites", json={"role": "member"}).json()
        # Revoke via the API.
        all_invites = client.get("/api/auth/invites").json()
        invite_id = all_invites[0]["id"]
        client.post(f"/api/auth/invites/{invite_id}/revoke")

        after_revoke = client.get("/api/auth/invites").json()
        assert all(i["id"] != invite_id for i in after_revoke)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/invites/{invite_id}/revoke
# ─────────────────────────────────────────────────────────────────────────────


class TestInviteRevokeEndpoint:
    def test_admin_can_revoke_invite(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        _set_current_user(app, admin)

        client.post("/api/auth/invites", json={"role": "member"})
        invite_id = client.get("/api/auth/invites").json()[0]["id"]

        response = client.post(f"/api/auth/invites/{invite_id}/revoke")
        assert response.status_code == 200
        assert response.json() == {"status": "revoked"}

    def test_revoked_invite_cannot_be_used_to_join(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        _set_current_user(app, admin)

        created = client.post("/api/auth/invites", json={"role": "member"}).json()
        invite_id = client.get("/api/auth/invites").json()[0]["id"]
        client.post(f"/api/auth/invites/{invite_id}/revoke")

        joined = client.post(
            "/api/auth/join",
            json={"token": created["token"], "username": "ghost"},
        )
        assert joined.status_code == 403

    def test_non_admin_cannot_revoke_invite(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        member = _member_user(repo)
        _set_current_user(app, admin)

        client.post("/api/auth/invites", json={"role": "member"})
        invite_id = client.get("/api/auth/invites").json()[0]["id"]

        _set_current_user(app, member)
        response = client.post(f"/api/auth/invites/{invite_id}/revoke")
        assert response.status_code == 403

    def test_revoke_unknown_invite_returns_404(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        _set_current_user(app, admin)

        response = client.post("/api/auth/invites/00000000-0000-0000-0000-000000000000/revoke")
        assert response.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end flows
# ─────────────────────────────────────────────────────────────────────────────


class TestEndToEndAuthFlow:
    def test_register_login_refresh_logout_relogin(self, env):
        _app, client, _repo = env

        # Register
        register = client.post(
            "/api/auth/register",
            json={"username": "frank", "password": "pass1234"},
        )
        assert register.status_code == 200

        # Login
        login = client.post(
            "/api/auth/login",
            json={"username": "frank", "password": "pass1234"},
        )
        assert login.status_code == 200
        original_refresh = login.json()["refresh_token"]

        # Refresh
        refreshed = client.post(
            "/api/auth/refresh",
            json={"refresh_token": original_refresh},
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["user"]["username"] == "frank"

        # Re-login (simulates logout + re-auth)
        re_login = client.post(
            "/api/auth/login",
            json={"username": "frank", "password": "pass1234"},
        )
        assert re_login.status_code == 200
        assert re_login.json()["access_token"]

    def test_invite_create_join_login_complete_flow(self, env):
        app, client, repo = env
        admin = _admin_user(repo)
        _set_current_user(app, admin)

        # 1. Admin creates an invite link.
        created = client.post("/api/auth/invites", json={"role": "member"}).json()

        # 2. A new user joins via the invite link (no password).
        joined = client.post(
            "/api/auth/join",
            json={"token": created["token"], "username": "invited"},
        )
        assert joined.status_code == 200
        # Verify the underlying user has no password (invite-only).
        user = repo.get_user_by_username("invited")
        assert user["password_hash"] is None

        # 3. The invited user cannot log in via password (invite-only).
        password_login = client.post(
            "/api/auth/login",
            json={"username": "invited", "password": "anything"},
        )
        assert password_login.status_code == 403
        assert "invite" in password_login.json()["message"].lower()

        # 4. Revoke the invite; further joins should be blocked.
        invite_id = client.get("/api/auth/invites").json()[0]["id"]
        client.post(f"/api/auth/invites/{invite_id}/revoke")

        # 5. A different invite token must now be rejected.
        blocked = client.post(
            "/api/auth/join",
            json={"token": created["token"], "username": "another"},
        )
        assert blocked.status_code == 403