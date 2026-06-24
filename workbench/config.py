from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkbenchSettings:
    root_dir: Path
    db_path: Path
    comfyui_url: str
    default_user: str
    default_role: str


def load_settings() -> WorkbenchSettings:
    root = Path(os.environ.get("WORKBENCH_ROOT", "~/.openclaw/shared-workbench")).expanduser()
    db_path = Path(os.environ.get("WORKBENCH_DB", str(root / "workbench.sqlite")))
    return WorkbenchSettings(
        root_dir=root,
        db_path=db_path,
        comfyui_url=os.environ.get("COMFYUI_URL", "http://192.168.7.75:8188").rstrip("/"),
        default_user=os.environ.get("WORKBENCH_DEFAULT_USER", "local-user"),
        default_role=os.environ.get("WORKBENCH_DEFAULT_ROLE", "admin"),
    )
