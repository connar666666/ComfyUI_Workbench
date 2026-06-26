# PostgreSQL and MinIO Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Workbench backend runtime from SQLite/local files to PostgreSQL/MinIO using the FrameWeave DBML model.

**Architecture:** Keep FastAPI services and route names stable, but replace the persistence layer with PostgreSQL connections and MinIO-backed storage. Repository SQL remains hand-written and is ported to PostgreSQL placeholders, UUID ids, JSONB values, and `RETURNING`.

**Tech Stack:** FastAPI, psycopg 3, PostgreSQL 16+, MinIO Python SDK, pytest.

---

### Task 1: Configuration and Storage Factory

**Files:**
- Modify: `pyproject.toml`
- Modify: `workbench/config.py`
- Modify: `workbench/storage.py`
- Modify: `workbench/api.py`
- Modify: `workbench/main.py`
- Test: `tests/test_config_storage.py`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

from workbench.config import load_settings
from workbench.storage import LocalStorage, build_storage


def test_postgres_and_minio_defaults(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    settings = load_settings()
    assert settings.database_url == "postgresql://lijiahao:123456@localhost:5432/postgres"
    assert settings.storage_backend == "minio"
    assert settings.minio_endpoint == "localhost:9000"
    assert settings.minio_access_key == "minio"
    assert settings.minio_secret_key == "minioadmin"
    assert settings.minio_bucket == "workbench"


def test_storage_factory_can_keep_local_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("WORKBENCH_ROOT", str(tmp_path))
    settings = load_settings()
    storage = build_storage(settings)
    assert isinstance(storage, LocalStorage)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_config_storage.py -q`

Expected: failure because `database_url`, MinIO fields, and `build_storage` do not exist.

- [ ] **Step 3: Implement minimal config and storage factory**

Add `psycopg[binary]` and `minio` to dependencies. Add settings fields and a `build_storage(settings)` helper returning `MinioStorage` by default or `LocalStorage` when `STORAGE_BACKEND=local`.

- [ ] **Step 4: Run test to verify pass**

Run: `uv run pytest tests/test_config_storage.py -q`

Expected: pass.

### Task 2: PostgreSQL Schema and Initialization

**Files:**
- Create: `workbench/schema_postgres.sql`
- Modify: `workbench/db.py`
- Modify: `workbench/scripts/init_db.py`
- Test: `tests/test_postgres_schema.py`

- [ ] **Step 1: Write failing schema tests**

```python
from pathlib import Path


def test_postgres_schema_contains_dbml_core_tables():
    sql = Path("workbench/schema_postgres.sql").read_text()
    for table in [
        "users",
        "projects",
        "canvases",
        "canvas_versions",
        "canvas_version_details",
        "oss_objects",
        "canvas_outputs",
        "project_asset_libraries",
        "asset_folders",
        "library_assets",
        "canvas_change_logs",
    ]:
        assert f"create table if not exists {table}" in sql
    assert "gen_random_uuid()" in sql
    assert "jsonb" in sql
```

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/test_postgres_schema.py -q`

Expected: failure because `schema_postgres.sql` does not exist.

- [ ] **Step 3: Implement PostgreSQL schema and initializer**

Create DBML core tables and compatibility tables. Add `connect_db(database_url)` using psycopg and `initialize_db(database_url, default_user, default_role)` that executes the PostgreSQL schema and seeds a default user.

- [ ] **Step 4: Run schema tests**

Run: `uv run pytest tests/test_postgres_schema.py -q`

Expected: pass.

### Task 3: Repository PostgreSQL Port

**Files:**
- Modify: `workbench/repositories.py`
- Modify: `workbench/services/folders.py`
- Modify: `workbench/auth.py`
- Modify: `workbench/routes_auth.py`
- Test: existing backend API tests

- [ ] **Step 1: Write failing repository tests for UUID ids**

Add a repository test that creates a user/project and asserts returned ids are strings.

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/test_projects_api.py -q`

Expected: failure until repository and test setup use PostgreSQL.

- [ ] **Step 3: Port SQL**

Replace SQLite placeholders with `%s`, replace `lastrowid` with `returning id`, convert JSON payloads through psycopg JSON adapters, and use PostgreSQL upsert syntax.

- [ ] **Step 4: Run API tests**

Run: `uv run pytest tests/test_projects_api.py tests/test_folders_api.py tests/test_api_queue.py tests/test_remote_workflows_api.py -q`

Expected: pass when `DATABASE_URL` points to a reachable test database, otherwise skip integration tests with a clear message.

### Task 4: MinIO Storage Runtime

**Files:**
- Modify: `workbench/storage.py`
- Modify: `workbench/api.py`
- Modify: `workbench/worker.py`
- Modify: `workbench/services/project_workflows.py`
- Test: `tests/test_config_storage.py`

- [ ] **Step 1: Write failing fake-client MinIO test**

Create a fake MinIO client with `bucket_exists`, `make_bucket`, `put_object`, and `get_object`, then assert `MinioStorage.store_asset()` returns `StoredFile` with an object key and sha256.

- [ ] **Step 2: Run test to verify failure**

Run: `uv run pytest tests/test_config_storage.py -q`

Expected: failure because `MinioStorage` has not been implemented.

- [ ] **Step 3: Implement MinIO storage**

Add `MinioStorage` methods matching existing `LocalStorage` methods: `ensure_layout`, `store_asset`, `archive_video`, `open`, and `resolve` compatibility where needed.

- [ ] **Step 4: Update file serving and worker reads**

Use storage `open()` for `/files/...`; keep local `resolve()` only for local backend. For ComfyUI file upload paths that require filesystem paths, materialize MinIO objects into the workbench tmp directory.

- [ ] **Step 5: Run storage tests**

Run: `uv run pytest tests/test_config_storage.py -q`

Expected: pass.

### Task 5: Final Verification

**Files:**
- All modified backend files

- [ ] **Step 1: Run unit tests**

Run: `uv run pytest -q`

Expected: pass or skip PostgreSQL integration tests when no database is configured.

- [ ] **Step 2: Initialize local PostgreSQL**

Run: `DATABASE_URL=postgresql://lijiahao:123456@localhost:5432/postgres uv run python -m workbench.scripts.init_db`

Expected: schema applies successfully against the user's Docker PostgreSQL container.

- [ ] **Step 3: Start API locally**

Run: `DATABASE_URL=postgresql://lijiahao:123456@localhost:5432/postgres STORAGE_BACKEND=minio uv run python -m workbench.main`

Expected: FastAPI starts on port 8090 and `/api/health` returns `{"status":"ok"}`.
