from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of workbench/ directory)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class WorkbenchSettings:
    root_dir: Path
    db_path: Path
    comfyui_url: str
    default_user: str
    default_role: str
    jwt_secret: str
    jwt_expiry_hours: int
    invite_token_bytes: int
    invite_expiry_days: int
    liveblocks_secret_key: str | None


def _dev_jwt_secret() -> str:
    """Generate a random secret for dev if not configured."""
    return os.environ.get("JWT_SECRET", "dev-" + secrets.token_hex(32))


def load_settings() -> WorkbenchSettings:
    root = Path(os.environ.get("WORKBENCH_ROOT", "~/.openclaw/shared-workbench")).expanduser()
    db_path = Path(os.environ.get("WORKBENCH_DB", str(root / "workbench.sqlite")))
    return WorkbenchSettings(
        root_dir=root,
        db_path=db_path,
        comfyui_url=os.environ.get("COMFYUI_URL", "http://192.168.7.75:8188").rstrip("/"),
        default_user=os.environ.get("WORKBENCH_DEFAULT_USER", "local-user"),
        default_role=os.environ.get("WORKBENCH_DEFAULT_ROLE", "admin"),
        jwt_secret=_dev_jwt_secret(),
        jwt_expiry_hours=int(os.environ.get("JWT_EXPIRY_HOURS", "24")),
        invite_token_bytes=int(os.environ.get("INVITE_TOKEN_BYTES", "32")),
        invite_expiry_days=int(os.environ.get("INVITE_EXPIRY_DAYS", "7")),
        liveblocks_secret_key=os.environ.get("LIVEBLOCKS_SECRET_KEY"),
    )
