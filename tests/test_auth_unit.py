from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest

from workbench.auth import (
    CurrentUser,
    _extract_bearer,
    create_access_token,
    create_refresh_token,
    current_user_from_headers,
    decode_token,
    generate_invite_token,
    get_current_user,
    hash_password,
    make_invite_link,
    verify_password,
)
from workbench.errors import PermissionDeniedError


class TestPasswordHashing:
    def test_hash_password_returns_pbkdf2_string(self):
        stored = hash_password("hunter2")

        assert stored.startswith("pbkdf2:")
        parts = stored.split(":")
        assert len(parts) == 3
        assert len(bytes.fromhex(parts[1])) == 32
        assert len(bytes.fromhex(parts[2])) == 32

    def test_hash_produces_unique_salts(self):
        a = hash_password("same")
        b = hash_password("same")
        assert a != b

    def test_verify_password_accepts_correct_password(self):
        stored = hash_password("correct horse")
        assert verify_password("correct horse", stored) is True

    def test_verify_password_rejects_wrong_password(self):
        stored = hash_password("right")
        assert verify_password("wrong", stored) is False

    def test_verify_password_returns_false_for_malformed_hash(self):
        for bad in ["", "not-a-hash", "pbkdf2:only-two:parts:extra", "pbkdf2:zz:nothex", "pbkdf2::"]:
            assert verify_password("anything", bad) is False

    def test_verify_password_returns_false_for_non_string(self):
        assert verify_password("anything", None) is False  # type: ignore[arg-type]


class TestAccessToken:
    def test_create_and_decode_roundtrip(self):
        token = create_access_token("user-1", "alice", "admin")
        payload = decode_token(token)

        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["username"] == "alice"
        assert payload["role"] == "admin"
        assert "exp" in payload
        assert "iat" in payload
        assert payload.get("typ") != "refresh"

    def test_decode_returns_none_for_garbage(self):
        assert decode_token("not.a.jwt") is None
        assert decode_token("") is None

    def test_decode_returns_none_for_wrong_signature(self):
        token = pyjwt.encode({"sub": "u", "username": "u", "role": "admin"}, "wrong-secret", algorithm="HS256")
        assert decode_token(token) is None

    def test_decode_returns_none_for_expired_token(self):
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "u",
            "username": "u",
            "role": "admin",
            "iat": now - timedelta(hours=48),
            "exp": now - timedelta(hours=24),
        }
        token = pyjwt.encode(payload, "test-secret", algorithm="HS256")
        assert decode_token(token) is None


class TestRefreshToken:
    def test_refresh_token_has_typ_marker(self):
        token = create_refresh_token("user-9")
        payload = decode_token(token)
        assert payload is not None
        assert payload["typ"] == "refresh"
        assert payload["sub"] == "user-9"


class TestInviteToken:
    def test_generate_invite_token_returns_plain_and_hash(self):
        plain, hashed = generate_invite_token()

        assert plain != hashed
        assert len(plain) > 0
        assert len(hashed) == 64

    def test_two_invite_tokens_are_unique(self):
        a = generate_invite_token()
        b = generate_invite_token()
        assert a[0] != b[0]
        assert a[1] != b[1]

    def test_make_invite_link_uses_supplied_base(self):
        link = make_invite_link("abc", "https://example.com:9000/")
        assert link == "https://example.com:9000/join?token=abc"

    def test_make_invite_link_strips_trailing_slash(self):
        link = make_invite_link("abc", "https://example.com/")
        assert link.startswith("https://example.com/join")


class TestBearerExtraction:
    def test_extracts_bearer_token(self):
        assert _extract_bearer("Bearer abc.def.ghi") == "abc.def.ghi"

    def test_returns_none_when_prefix_missing(self):
        assert _extract_bearer("Token abc") is None
        assert _extract_bearer("") is None

    def test_none_header_raises_attribute_error(self):
        # _extract_bearer is a plain helper that does not handle None; the FastAPI
        # dependency layer is what supplies the default when the header is missing.
        with pytest.raises(AttributeError):
            _extract_bearer(None)  # type: ignore[arg-type]


class TestGetCurrentUserDependency:
    def test_returns_current_user_when_token_valid(self):
        token = create_access_token("user-1", "alice", "admin")
        user = get_current_user(authorization=f"Bearer {token}")
        assert isinstance(user, CurrentUser)
        assert user.id == "user-1"
        assert user.username == "alice"
        assert user.role == "admin"

    def test_raises_when_header_missing(self):
        with pytest.raises(PermissionDeniedError):
            get_current_user(authorization="")

    def test_raises_when_token_invalid(self):
        with pytest.raises(PermissionDeniedError):
            get_current_user(authorization="Bearer garbage")

    def test_raises_when_refresh_token_used_as_access(self):
        token = create_refresh_token("user-1")
        with pytest.raises(PermissionDeniedError):
            get_current_user(authorization=f"Bearer {token}")


class TestLegacyHeaderAuth:
    def test_uses_supplied_headers(self):
        user = current_user_from_headers(
            x_workbench_user="bob",
            x_workbench_user_id="12345678-1234-1234-1234-123456789012",
            x_workbench_role="member",
        )
        assert user.username == "bob"
        assert user.id == "12345678-1234-1234-1234-123456789012"
        assert user.role == "member"

    def test_invalid_role_falls_back_to_admin(self):
        user = current_user_from_headers(x_workbench_role="superuser")
        assert user.role == "admin"

    def test_unknown_role_falls_back_to_admin_when_role_invalid(self):
        # Valid roles are 'member' or 'admin'; anything else yields admin.
        user = current_user_from_headers(x_workbench_user="bob", x_workbench_role="editor")
        assert user.role == "admin"