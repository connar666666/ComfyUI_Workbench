"""Auth routes: invite-link join, JWT login/refresh, user management."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .auth import (
    CurrentUser,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_invite_token,
    get_current_user,
    hash_password,
    make_invite_link,
    verify_password,
)
from .errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError, WorkbenchError
from .repositories import WorkbenchRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Request / response models ──────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class JoinRequest(BaseModel):
    token: str
    username: str
    display_name: str | None = None


class InviteCreateRequest(BaseModel):
    role: str = "member"
    max_uses: int | None = None
    expires_in_days: int = 7


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: dict


def _user_dict(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name", user["username"]),
        "role": user["role"],
    }


def _tokens_for(user: dict) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user["id"], user["username"], user["role"]),
        refresh_token=create_refresh_token(user["id"]),
        user=_user_dict(user),
    )


def _get_repo() -> WorkbenchRepository:
    from .config import load_settings
    return WorkbenchRepository(load_settings().database_url)


# ── Invite-link join ───────────────────────────────────────────────────────

@router.post("/join", response_model=TokenResponse)
def join_via_invite(req: JoinRequest):
    """Join the workspace using an invite token. Creates a user account."""
    repo = _get_repo()
    token_hash = hashlib.sha256(req.token.encode()).hexdigest()

    invite = repo.get_invite_by_hash(token_hash)
    if invite is None:
        raise PermissionDeniedError("Invalid or expired invite link")

    if not repo.use_invite(token_hash):
        raise PermissionDeniedError("Invite link has been exhausted or expired")

    display_name = req.display_name or req.username
    try:
        user = repo.create_user(
            username=req.username,
            display_name=display_name,
            password_hash=None,  # no password — invite-only login
            role=invite["role"],
        )
    except ConflictError:
        # User already exists — just log them in with the existing account
        user = repo.get_user_by_username(req.username)
        if user["role"] != invite["role"]:
            pass  # keep existing role

    repo.update_last_seen(user["id"])
    return _tokens_for(user)


# ── Username + password register (admin-created accounts) ──────────────────

@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    """Register with username + password. Only works if the default admin hasn't set a password yet, or for creating additional accounts."""
    if len(req.username) < 2:
        raise ValidationError("Username must be at least 2 characters")
    if len(req.password) < 4:
        raise ValidationError("Password must be at least 4 characters")

    repo = _get_repo()
    try:
        user = repo.create_user(
            username=req.username,
            display_name=req.display_name or req.username,
            password_hash=hash_password(req.password),
            role="member",
        )
    except ConflictError:
        raise ConflictError(f"Username '{req.username}' is already taken")

    repo.update_last_seen(user["id"])
    return _tokens_for(user)


# ── Login ──────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """Login with username + password."""
    repo = _get_repo()
    try:
        user = repo.get_user_by_username(req.username)
    except Exception:
        raise PermissionDeniedError("Invalid username or password")

    if user.get("password_hash"):
        if not verify_password(req.password, user["password_hash"]):
            raise PermissionDeniedError("Invalid username or password")
    else:
        # User was created via invite and has no password
        raise PermissionDeniedError("This account uses invite-only login. Use your invite link to sign in.")

    repo.update_last_seen(user["id"])
    return _tokens_for(user)


# ── Token refresh ──────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest):
    """Get a new access token using a refresh token."""
    payload = decode_token(req.refresh_token)
    if payload is None or payload.get("typ") != "refresh":
        raise PermissionDeniedError("Invalid or expired refresh token")

    repo = _get_repo()
    user = repo.get_user_by_id(str(payload["sub"]))
    repo.update_last_seen(user["id"])
    return _tokens_for(user)


# ── Current user info ──────────────────────────────────────────────────────

@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    """Return current authenticated user."""
    repo = _get_repo()
    u = repo.get_user_by_id(user.id)
    return _user_dict(u)


# ── Invite management (admin only) ─────────────────────────────────────────

@router.post("/invites")
def create_invite(
    req: InviteCreateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Create an invite link. Admin only."""
    if user.role != "admin":
        raise PermissionDeniedError("Only admins can create invite links")

    repo = _get_repo()
    plaintext, token_hash = generate_invite_token()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=req.expires_in_days)).isoformat() if req.expires_in_days > 0 else None

    repo.create_invite(
        token_hash=token_hash,
        created_by=user.id,
        role=req.role,
        max_uses=req.max_uses,
        expires_at=expires_at,
    )

    link = make_invite_link(plaintext)
    return {"invite_link": link, "token": plaintext, "role": req.role, "expires_in_days": req.expires_in_days}


@router.get("/invites")
def list_invites(user: CurrentUser = Depends(get_current_user)):
    """List active invite links. Admin sees all, members see theirs."""
    repo = _get_repo()
    invites = repo.list_invites(created_by=user.id if user.role != "admin" else None)
    return [dict(i) for i in invites]


@router.post("/invites/{invite_id}/revoke")
def revoke_invite(invite_id: str, user: CurrentUser = Depends(get_current_user)):
    """Revoke an invite link by ID."""
    if user.role != "admin":
        raise PermissionDeniedError("Only admins can revoke invite links")
    repo = _get_repo()
    # Find the invite by ID and revoke by its token_hash
    invites = repo.list_invites()
    for inv in invites:
        if inv["id"] == invite_id:
            repo.revoke_invite(inv["token_hash"])
            return {"status": "revoked"}
    raise NotFoundError(invite_id)
