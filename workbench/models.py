from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AssetKind = Literal["image", "audio", "video", "document"]
FolderScope = Literal["assets", "videos"]
JobStatus = Literal["queued", "running", "succeeded", "failed", "canceled"]
UserRole = Literal["member", "admin"]
ProjectRole = Literal["owner", "editor", "viewer"]


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    size_bytes: int
    sha256: str
