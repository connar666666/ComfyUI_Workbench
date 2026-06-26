# PostgreSQL and MinIO Migration Design

## Summary

Migrate the Workbench backend from SQLite plus local filesystem storage to PostgreSQL plus MinIO, using the provided FrameWeave DBML as the target database model. This is a full backend storage migration, but the public FastAPI route shape should stay as stable as possible so the existing frontend can be updated incrementally.

## Goals

- Use PostgreSQL as the runtime database.
- Use MinIO as the runtime object store.
- Convert the DBML into an executable PostgreSQL schema.
- Preserve existing API route names and response shapes where practical.
- Store files as MinIO objects and keep durable object metadata in PostgreSQL.
- Keep the existing project, asset, job, video, folder, and canvas version flows working after the storage change.

## Non-Goals

- Do not migrate historical SQLite rows in this pass.
- Do not introduce an ORM.
- Do not redesign the frontend UX.
- Do not add Neo4j integration beyond storing the DBML graph namespace fields.
- Do not expose presigned URLs as canonical database state.

## Architecture

The backend becomes PostgreSQL-first. `workbench/db.py` owns connection creation, schema initialization, row conversion, and timestamp helpers. Repository methods continue to use hand-written SQL, but their statements are ported to PostgreSQL placeholders, JSONB handling, `RETURNING`, and UUID ids.

MinIO replaces direct filesystem persistence behind the existing storage service boundary. `workbench/storage.py` exposes a storage interface implemented by `MinioStorage`; file streaming routes fetch object bytes from MinIO and continue to serve through existing `/files/assets/{id}` and `/files/videos/{id}` endpoints.

## Database Model

The new PostgreSQL schema follows the provided DBML and includes:

- `users`
- `projects`
- `project_members`
- `canvases`
- `canvas_versions`
- `canvas_version_details`
- `oss_objects`
- `canvas_outputs`
- `project_asset_libraries`
- `asset_folders`
- `library_assets`
- `canvas_change_logs`

Compatibility tables for existing Workbench behavior are retained in PostgreSQL:

- `invite_tokens`
- `tags`
- `asset_tags`
- `generation_jobs`
- `remote_workflow_runs`
- `project_workflows`
- `job_inputs`
- `comfyui_tasks`
- `videos`
- `node_versions`
- `video_tags`
- `audit_events`

Where DBML and current Workbench overlap, DBML tables are canonical for new asset-library and canvas structures, while compatibility tables keep existing UI and worker flows functional.

## Identifier Strategy

DBML tables use UUID primary keys, with `gen_random_uuid()` defaults. Existing compatibility tables also move to UUID ids so the backend has one id strategy. API payloads will expose ids as strings. Frontend numeric assumptions are expected to be updated separately where needed.

Canvas version ids use text ids formatted by the backend. Existing node-version compatibility ids use UUID ids.

## Storage Model

Uploaded or generated files are written to MinIO. Object metadata is recorded in `oss_objects`. Compatibility `assets` and `videos` rows also store `oss_object_id` and a stable `storage_key` for existing service code.

Default development settings target the user's local containers:

- PostgreSQL: `postgresql://lijiahao:123456@localhost:5432/postgres`
- MinIO endpoint: `http://localhost:9000`
- MinIO root user: `minio`
- MinIO root password: `minioadmin`
- Default bucket: `workbench`

## Runtime Configuration

`WorkbenchSettings` gains:

- `database_url`
- `storage_backend`
- `minio_endpoint`
- `minio_access_key`
- `minio_secret_key`
- `minio_bucket`
- `minio_secure`

`storage_backend=minio` is the new default for this migration.

## API Compatibility

Existing routes remain in place:

- `/api/projects`
- `/api/assets`
- `/api/projects/{project_id}/assets`
- `/api/jobs`
- `/api/canvas/{canvas_id}/versions`
- `/api/canvas/{canvas_id}/nodes/{node_id}/versions`
- `/files/assets/{asset_id}`
- `/files/videos/{video_id}`

The main compatibility break is id type: ids become strings because PostgreSQL uses UUID. The backend should not cast UUIDs to integers.

## Error Handling

Database uniqueness and FK errors should continue to map to existing `ConflictError`, `NotFoundError`, and `ValidationError` where services already depend on them. MinIO upload/read failures should raise `ServiceUnavailableError` or `ValidationError` depending on whether the issue is infrastructure or invalid input.

## Testing

Unit tests should cover:

- Settings load PostgreSQL and MinIO defaults.
- PostgreSQL SQL generation and row conversion behaviors.
- MinIO storage writes deterministic metadata without requiring a live MinIO server by using a fake client.
- Repository methods use UUID ids and PostgreSQL-style results.

Existing API tests should be ported from temp SQLite paths to an isolated PostgreSQL test database only if a database URL is available; otherwise they should be skipped with a clear reason.
