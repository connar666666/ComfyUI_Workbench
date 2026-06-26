from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from fastapi import Header

from .config import load_settings
from .models import UserRole


@dataclass(frozen=True)
class CurrentUser:
    id: str
    username: str
    role: UserRole


# ── Password hashing (simple pbkdf2 via hashlib — no extra deps) ──────────

_SALT_LEN = 32
_ITERATIONS = 600_000
_DKLEN = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_LEN)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS, dklen=_DKLEN)
    return f"pbkdf2:{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, salt_hex, dk_hex = stored.split(":", 2)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS, dklen=_DKLEN)
        return hmac.compare_digest(actual, expected)
    except (ValueError, AttributeError):
        return False


# ── JWT ────────────────────────────────────────────────────────────────────

_settings = load_settings()
_JWT_SECRET = _settings.jwt_secret
_JWT_ALG = "HS256"


def create_access_token(user_id: str, username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=_settings.jwt_expiry_hours),
    }
    return pyjwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALG)


def create_refresh_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "typ": "refresh",
        "iat": now,
        "exp": now + timedelta(days=7),
    }
    return pyjwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALG)


def decode_token(token: str) -> dict | None:
    try:
        return pyjwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALG])
    except pyjwt.PyJWTError:
        return None


# ── Invite tokens ──────────────────────────────────────────────────────────

def generate_invite_token() -> tuple[str, str]:
    """Return (plaintext_token, sha256_hash_of_token)."""
    raw = secrets.token_hex(_settings.invite_token_bytes)
    h = hashlib.sha256(raw.encode()).hexdigest()
    return raw, h


def make_invite_link(plaintext: str, base_url: str | None = None) -> str:
    """Build a join URL like http://host:port/join?token=<plaintext>."""
    base = base_url or "http://localhost:5174"
    return f"{base.rstrip('/')}/join?token={plaintext}"


# ── FastAPI dependency (JWT from Authorization header) ─────────────────────

def get_current_user(authorization: str = Header(default="")) -> CurrentUser:
    """FastAPI dependency: extracts and validates JWT Bearer token."""
    token = _extract_bearer(authorization)
    if token is None:
        from .errors import PermissionDeniedError
        raise PermissionDeniedError("Missing or invalid Authorization header")

    payload = decode_token(token)
    if payload is None or payload.get("typ") == "refresh":
        from .errors import PermissionDeniedError
        raise PermissionDeniedError("Invalid or expired token")

    return CurrentUser(
        id=str(payload["sub"]),
        username=payload["username"],
        role=payload["role"],  # type: ignore[arg-type]
    )


def _extract_bearer(header: str) -> str | None:
    if not header.startswith("Bearer "):
        return None
    return header[7:]


# ── Legacy header-based auth (backward compat) ─────────────────────────────

def current_user_from_headers(
    x_workbench_user: str | None = Header(default=None),
    x_workbench_user_id: str | None = Header(default=None),
    x_workbench_role: str | None = Header(default=None),
) -> CurrentUser:
    username = x_workbench_user or "local-user"
    user_id = x_workbench_user_id or "00000000-0000-0000-0000-000000000000"
    role = x_workbench_role if x_workbench_role in ("member", "admin") else "admin"
    return CurrentUser(id=user_id, username=username, role=role)  # type: ignore[arg-type]
