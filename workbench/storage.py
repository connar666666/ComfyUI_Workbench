from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from .models import AssetKind, StoredFile


ASSET_DIRS: dict[AssetKind, str] = {
    "image": "images",
    "audio": "audio",
    "video": "videos",
    "document": "documents",
}


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root

    def ensure_layout(self) -> None:
        for rel in [
            "assets/images",
            "assets/audio",
            "assets/videos",
            "assets/documents",
            "outputs/videos",
            "derived/thumbnails",
            "derived/waveforms",
            "tmp",
        ]:
            (self.root / rel).mkdir(parents=True, exist_ok=True)

    def resolve(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("storage key escapes workbench root")
        return path

    def store_asset(self, kind: AssetKind, filename: str, stream: BinaryIO) -> StoredFile:
        self.ensure_layout()
        suffix = Path(filename).suffix.lower()
        storage_key = f"assets/{ASSET_DIRS[kind]}/{uuid.uuid4().hex}{suffix}"
        return self._write_stream(storage_key, stream)

    def archive_video(self, source_path: Path, filename: str) -> StoredFile:
        self.ensure_layout()
        suffix = Path(filename).suffix.lower() or ".mp4"
        storage_key = f"outputs/videos/{uuid.uuid4().hex}{suffix}"
        dest = self.resolve(storage_key)
        shutil.copy2(source_path, dest)
        return self._stat_file(storage_key)

    def _write_stream(self, storage_key: str, stream: BinaryIO) -> StoredFile:
        dest = self.resolve(storage_key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        with dest.open("wb") as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
        return StoredFile(storage_key=storage_key, size_bytes=size, sha256=digest.hexdigest())

    def _stat_file(self, storage_key: str) -> StoredFile:
        path = self.resolve(storage_key)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return StoredFile(storage_key=storage_key, size_bytes=path.stat().st_size, sha256=digest)
