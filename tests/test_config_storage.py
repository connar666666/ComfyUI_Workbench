from __future__ import annotations

from io import BytesIO

from workbench.config import load_settings
from workbench.storage import LocalStorage, MinioStorage, build_storage


def test_postgres_and_minio_defaults(monkeypatch):
    for key in [
        "DATABASE_URL",
        "STORAGE_BACKEND",
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_BUCKET",
        "MINIO_SECURE",
    ]:
        monkeypatch.delenv(key, raising=False)

    settings = load_settings()

    assert settings.database_url == "postgresql://lijiahao:123456@localhost:5432/postgres"
    assert settings.storage_backend == "minio"
    assert settings.minio_endpoint == "localhost:9000"
    assert settings.minio_access_key == "minio"
    assert settings.minio_secret_key == "minioadmin"
    assert settings.minio_bucket == "workbench"
    assert settings.minio_secure is False


def test_storage_factory_can_keep_local_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("WORKBENCH_ROOT", str(tmp_path))

    settings = load_settings()
    storage = build_storage(settings)

    assert isinstance(storage, LocalStorage)


class FakeMinioClient:
    def __init__(self):
        self.buckets: set[str] = set()
        self.objects: dict[tuple[str, str], bytes] = {}

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def put_object(self, bucket: str, object_key: str, payload, size: int) -> None:
        self.objects[(bucket, object_key)] = payload.read(size)


def test_minio_storage_stores_asset_and_returns_metadata():
    client = FakeMinioClient()
    storage = MinioStorage(
        endpoint="localhost:9000",
        access_key="minio",
        secret_key="minioadmin",
        bucket="workbench",
        client=client,
    )

    stored = storage.store_asset("image", "sample.png", BytesIO(b"image-bytes"))

    assert stored.storage_key.startswith("assets/images/")
    assert stored.storage_key.endswith(".png")
    assert stored.size_bytes == 11
    assert stored.sha256 == "2c8648d103e3dd7ad87660da0f126a1443b6d21ac1bd3ec000c5e24e2373a90c"
    assert client.objects[("workbench", stored.storage_key)] == b"image-bytes"
