from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest

from workbench.models import StoredFile
from workbench.storage import ASSET_DIRS, LocalStorage


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "scratch").mkdir()
    return tmp_path


@pytest.fixture
def storage(root: Path) -> LocalStorage:
    return LocalStorage(root=root)


class TestEnsureLayout:
    def test_creates_all_known_directories(self, storage: LocalStorage, root: Path):
        storage.ensure_layout()

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
            assert (root / rel).is_dir()

    def test_is_idempotent(self, storage: LocalStorage):
        storage.ensure_layout()
        storage.ensure_layout()
        # Should still have the layout after a second call.
        assert (storage.root / "assets" / "images").is_dir()


class TestStoreAsset:
    @pytest.mark.parametrize("kind, subdir", list(ASSET_DIRS.items()))
    def test_stores_under_correct_subdir(self, storage: LocalStorage, root: Path, kind: str, subdir: str):
        stored = storage.store_asset(kind, "clip.bin", BytesIO(b"hello"))

        assert stored.storage_key.startswith(f"assets/{subdir}/")
        assert stored.storage_key.endswith(".bin")
        assert stored.size_bytes == 5
        assert stored.sha256 == hashlib.sha256(b"hello").hexdigest()
        written_path = root / stored.storage_key
        assert written_path.read_bytes() == b"hello"

    def test_preserves_filename_suffix(self, storage: LocalStorage):
        stored = storage.store_asset("image", "photo.JPG", BytesIO(b"x"))
        # The implementation lowercases the suffix; that's fine because browsers
        # and CDNs are case-insensitive on extensions.
        assert stored.storage_key.endswith(".jpg")

    def test_generates_unique_keys(self, storage: LocalStorage):
        keys = {storage.store_asset("image", "a.png", BytesIO(b"1")).storage_key for _ in range(10)}
        assert len(keys) == 10

    def test_empty_filename_keeps_no_suffix(self, storage: LocalStorage):
        stored = storage.store_asset("document", "noext", BytesIO(b"data"))
        # No suffix in the input filename -> key has no extension.
        assert "." not in Path(stored.storage_key).name

    def test_chunked_stream_produces_correct_hash(self, storage: LocalStorage, root: Path):
        payload = b"".join(bytes([i % 256]) for i in range(3 * 1024 * 1024 + 17))  # > 1 MB to span chunks

        stored = storage.store_asset("image", "big.bin", BytesIO(payload))

        assert stored.size_bytes == len(payload)
        assert stored.sha256 == hashlib.sha256(payload).hexdigest()


class TestResolve:
    def test_resolves_inside_root(self, storage: LocalStorage, root: Path):
        path = storage.resolve("assets/images/x.png")
        assert path == (root / "assets" / "images" / "x.png").resolve()

    def test_rejects_escape_attempt(self, storage: LocalStorage):
        with pytest.raises(ValueError):
            storage.resolve("../escape.txt")

    def test_rejects_absolute_escape(self, storage: LocalStorage):
        with pytest.raises(ValueError):
            storage.resolve("/etc/passwd")


class TestArchiveVideo:
    def test_copies_source_file_into_outputs(self, storage: LocalStorage, root: Path, tmp_path: Path):
        source = tmp_path / "source.mp4"
        source.write_bytes(b"video-bytes")

        stored = storage.archive_video(source, "result.mp4")

        assert stored.storage_key.startswith("outputs/videos/")
        assert stored.storage_key.endswith(".mp4")
        assert stored.size_bytes == len(b"video-bytes")
        assert stored.sha256 == hashlib.sha256(b"video-bytes").hexdigest()
        assert (root / stored.storage_key).read_bytes() == b"video-bytes"

    def test_adds_default_extension_when_missing(self, storage: LocalStorage):
        # Source without a recognized video extension in the filename.
        src = storage.root / "tmp" / "raw"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"x")

        stored = storage.archive_video(src, "rawfile")

        assert stored.storage_key.endswith(".mp4")


class TestStoredFileDataclass:
    def test_is_frozen(self):
        sf = StoredFile(storage_key="k", size_bytes=1, sha256="abc")
        with pytest.raises(Exception):
            sf.size_bytes = 2  # type: ignore[misc]