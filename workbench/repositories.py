from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import connect_db, utc_now
from .errors import ConflictError, NotFoundError, PermissionDeniedError


class WorkbenchRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    # ── Users ──────────────────────────────────────────────────────────

    def get_user_by_username(self, username: str) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from users where username = ?", (username,)).fetchone()
        if row is None:
            raise NotFoundError(f"user '{username}'")
        return dict(row)

    def get_user_by_id(self, user_id: int) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from users where id = ?", (user_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"user #{user_id}")
        return dict(row)

    def create_user(
        self,
        *,
        username: str,
        display_name: str,
        password_hash: str | None = None,
        role: str = "member",
    ) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            existing = conn.execute("select id from users where username = ?", (username,)).fetchone()
            if existing:
                raise ConflictError(f"username '{username}' already exists")
            cur = conn.execute(
                """
                insert into users(username, display_name, role, password_hash, last_seen_at, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (username, display_name, role, password_hash, now, now, now),
            )
            conn.commit()
            return self.get_user_by_id(cur.lastrowid)

    def update_last_seen(self, user_id: int) -> None:
        with connect_db(self.db_path) as conn:
            conn.execute("update users set last_seen_at = ? where id = ?", (utc_now(), user_id))
            conn.commit()

    def list_users(self) -> list[dict[str, Any]]:
        with connect_db(self.db_path) as conn:
            return [dict(row) for row in conn.execute("select id, username, display_name, role, last_seen_at, created_at from users order by id").fetchall()]

    # ── Invite tokens ──────────────────────────────────────────────────

    def create_invite(
        self,
        *,
        token_hash: str,
        created_by: int,
        role: str = "member",
        max_uses: int | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cur = conn.execute(
                """
                insert into invite_tokens(token_hash, created_by, role, max_uses, expires_at, created_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (token_hash, created_by, role, max_uses, expires_at, now),
            )
            conn.commit()
            return dict(conn.execute("select * from invite_tokens where id = ?", (cur.lastrowid,)).fetchone())

    def get_invite_by_hash(self, token_hash: str) -> dict[str, Any] | None:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "select * from invite_tokens where token_hash = ? and is_revoked = 0",
                (token_hash,),
            ).fetchone()
        return dict(row) if row else None

    def use_invite(self, token_hash: str) -> bool:
        """Increment use_count. Returns True if still valid, False if exhausted/expired."""
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "select * from invite_tokens where token_hash = ? and is_revoked = 0",
                (token_hash,),
            ).fetchone()
            if row is None:
                return False
            r = dict(row)
            from datetime import datetime, timezone
            if r["expires_at"] and r["expires_at"] < datetime.now(timezone.utc).isoformat():
                return False
            if r["max_uses"] is not None and r["use_count"] >= r["max_uses"]:
                return False
            conn.execute(
                "update invite_tokens set use_count = use_count + 1 where token_hash = ?",
                (token_hash,),
            )
            conn.commit()
            return True

    def revoke_invite(self, token_hash: str) -> None:
        with connect_db(self.db_path) as conn:
            conn.execute("update invite_tokens set is_revoked = 1 where token_hash = ?", (token_hash,))
            conn.commit()

    def list_invites(self, created_by: int | None = None) -> list[dict[str, Any]]:
        with connect_db(self.db_path) as conn:
            if created_by is not None:
                rows = conn.execute(
                    "select * from invite_tokens where created_by = ? and is_revoked = 0 order by created_at desc",
                    (created_by,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "select * from invite_tokens where is_revoked = 0 order by created_at desc"
                ).fetchall()
            return [dict(row) for row in rows]

    # ── Assets ─────────────────────────────────────────────────────────

    def create_asset(
        self,
        *,
        kind: str,
        original_filename: str,
        storage_key: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        uploaded_by: int,
        folder_id: int | None,
    ) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cur = conn.execute(
                """
                insert into assets(folder_id, kind, original_filename, storage_key, mime_type,
                                   size_bytes, sha256, uploaded_by, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (folder_id, kind, original_filename, storage_key, mime_type, size_bytes, sha256, uploaded_by, now, now),
            )
            conn.commit()
            return self.get_asset(cur.lastrowid)

    def get_asset(self, asset_id: int) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from assets where id = ? and deleted_at is null", (asset_id,)).fetchone()
        if row is None:
            raise NotFoundError(asset_id)
        return dict(row)

    def list_assets(
        self,
        kind: str | None = None,
        user_id: int | None = None,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "select a.*, u.username as uploaded_by_username from assets a left join users u on a.uploaded_by = u.id where a.deleted_at is null"
        params: list[Any] = []
        if kind:
            sql += " and a.kind = ?"
            params.append(kind)
        if role != "admin" and user_id is not None:
            sql += " and a.uploaded_by = ?"
            params.append(user_id)
        sql += " order by a.created_at desc, a.id desc"
        with connect_db(self.db_path) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    # ── Jobs ───────────────────────────────────────────────────────────

    def create_job(
        self,
        *,
        created_by: int,
        prompt: str,
        duration_sec: int,
        resolution: str,
        audio_start_sec: float,
        reference_image_asset_id: int | None,
        reference_audio_asset_id: int | None,
        replace_audio_asset_id: int | None,
        canvas_id: str | None = None,
        canvas_node_id: str | None = None,
        canvas_version_id: int | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cur = conn.execute(
                """
                insert into generation_jobs(
                  created_by, status, prompt, duration_sec, resolution, audio_start_sec,
                  reference_image_asset_id, reference_audio_asset_id, replace_audio_asset_id,
                  canvas_id, canvas_node_id, canvas_version_id, created_at, updated_at
                )
                values (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_by,
                    prompt,
                    duration_sec,
                    resolution,
                    audio_start_sec,
                    reference_image_asset_id,
                    reference_audio_asset_id,
                    replace_audio_asset_id,
                    canvas_id,
                    canvas_node_id,
                    canvas_version_id,
                    now,
                    now,
                ),
            )
            job_id = cur.lastrowid
            for asset_id, role_name in [
                (reference_image_asset_id, "reference_image"),
                (reference_audio_asset_id, "reference_audio"),
                (replace_audio_asset_id, "replace_audio"),
            ]:
                if asset_id is not None:
                    conn.execute(
                        "insert into job_inputs(job_id, asset_id, role, created_at) values (?, ?, ?, ?)",
                        (job_id, asset_id, role_name, now),
                    )
            conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: int) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "select j.*, u.username as created_by_username from generation_jobs j left join users u on j.created_by = u.id where j.id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(job_id)
        return dict(row)

    def list_jobs(
        self,
        user_id: int | None = None,
        role: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "select j.*, u.username as created_by_username from generation_jobs j left join users u on j.created_by = u.id"
        params: list[Any] = []
        conditions: list[str] = []
        if role != "admin" and user_id is not None:
            conditions.append("j.created_by = ?")
            params.append(user_id)
        if conditions:
            sql += " where " + " and ".join(conditions)
        sql += " order by j.created_at desc, j.id desc"
        with connect_db(self.db_path) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def next_node_version_number(self, canvas_id: str, node_id: str) -> int:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "select coalesce(max(version_number), 0) + 1 as next_version "
                "from node_versions where canvas_id = ? and node_id = ?",
                (canvas_id, node_id),
            ).fetchone()
        return int(row["next_version"])

    def create_node_version(
        self,
        *,
        canvas_id: str,
        node_id: str,
        generation_job_id: int,
        output_video_id: int | None,
        prompt: str,
        input_asset_ids: list[int],
        params: dict[str, Any],
        snapshot: dict[str, Any],
        status: str,
        created_by: int,
        parent_version_id: int | None = None,
        negative_prompt: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        version_number = self.next_node_version_number(canvas_id, node_id)
        with connect_db(self.db_path) as conn:
            cur = conn.execute(
                """
                insert into node_versions(
                  canvas_id, node_id, generation_job_id, output_video_id, version_number,
                  parent_version_id, prompt, negative_prompt, input_asset_ids_json,
                  params_json, snapshot_json, status, created_by, created_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    canvas_id,
                    node_id,
                    generation_job_id,
                    output_video_id,
                    version_number,
                    parent_version_id,
                    prompt,
                    negative_prompt,
                    json.dumps(input_asset_ids, ensure_ascii=False),
                    json.dumps(params, ensure_ascii=False),
                    json.dumps(snapshot, ensure_ascii=False),
                    status,
                    created_by,
                    now,
                ),
            )
            conn.commit()
            row = conn.execute("select * from node_versions where id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def list_node_versions(self, canvas_id: str, node_id: str | None = None) -> list[dict[str, Any]]:
        sql = "select * from node_versions where canvas_id = ?"
        params: list[Any] = [canvas_id]
        if node_id is not None:
            sql += " and node_id = ?"
            params.append(node_id)
        sql += " order by created_at desc, id desc"
        with connect_db(self.db_path) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def claim_next_job(self) -> dict[str, Any] | None:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "update generation_jobs set status = 'running', started_at = ?, updated_at = ? "
                "where id = (select id from generation_jobs where status = 'queued' "
                "order by created_at asc, id asc limit 1) "
                "returning *",
                (now, now),
            ).fetchone()
            if row is None:
                return None
            conn.commit()
            return dict(row)

    def record_comfyui_task(self, *, job_id: int | None, prompt_id: str, comfyui_url: str, native_status: str, raw_summary: dict[str, Any] | None = None) -> dict[str, Any]:
        now = utc_now()
        raw = json.dumps(raw_summary or {}, ensure_ascii=False)
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                insert into comfyui_tasks(job_id, prompt_id, comfyui_url, native_status, raw_summary_json, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(prompt_id) do update set
                  job_id = excluded.job_id,
                  native_status = excluded.native_status,
                  raw_summary_json = excluded.raw_summary_json,
                  updated_at = excluded.updated_at
                """,
                (job_id, prompt_id, comfyui_url, native_status, raw, now, now),
            )
            conn.commit()
            row = conn.execute("select * from comfyui_tasks where prompt_id = ?", (prompt_id,)).fetchone()
            return dict(row)

    def mark_job_failed(self, job_id: int, error_code: str, error_message: str) -> None:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update generation_jobs set status = 'failed', error_code = ?, error_message = ?, completed_at = ?, updated_at = ? where id = ?",
                (error_code, error_message, now, now, job_id),
            )
            conn.commit()

    def mark_job_succeeded(self, job_id: int, output_video_id: int | None = None) -> None:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update generation_jobs set status = 'succeeded', output_video_id = ?, completed_at = ?, updated_at = ? where id = ?",
                (output_video_id, now, now, job_id),
            )
            conn.commit()

    def set_job_canvas_version(self, job_id: int, canvas_version_id: int) -> None:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update generation_jobs set canvas_version_id = ?, updated_at = ? where id = ?",
                (canvas_version_id, now, job_id),
            )
            conn.commit()

    def cancel_job(self, job_id: int, user_id: int | None = None, role: str | None = None) -> None:
        """Cancel a queued job. Admin can cancel any; member only their own."""
        now = utc_now()
        with connect_db(self.db_path) as conn:
            job = conn.execute(
                "select * from generation_jobs where id = ? and status = 'queued'",
                (job_id,),
            ).fetchone()
            if job is None:
                raise NotFoundError(job_id)
            if role != "admin" and user_id is not None and job["created_by"] != user_id:
                raise PermissionDeniedError("Cannot cancel another user's job")
            conn.execute(
                "update generation_jobs set status = 'canceled', completed_at = ?, updated_at = ? where id = ? and status = 'queued'",
                (now, now, job_id),
            )
            conn.commit()

    # ── Videos ─────────────────────────────────────────────────────────

    def create_video(
        self,
        *,
        source_job_id: int,
        created_by: int,
        title: str,
        storage_key: str,
        mime_type: str,
        size_bytes: int,
        duration_sec: float | None = None,
        width: int | None = None,
        height: int | None = None,
        prompt: str = "",
    ) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cur = conn.execute(
                """
                insert into videos(source_job_id, created_by, title, storage_key, mime_type,
                                   size_bytes, duration_sec, width, height, prompt, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (source_job_id, created_by, title, storage_key, mime_type, size_bytes, duration_sec, width, height, prompt, now, now),
            )
            conn.commit()
            return dict(conn.execute("select * from videos where id = ?", (cur.lastrowid,)).fetchone())

    def list_videos(self) -> list[dict[str, Any]]:
        with connect_db(self.db_path) as conn:
            return [dict(row) for row in conn.execute(
                "select v.*, u.username as created_by_username from videos v left join users u on v.created_by = u.id where v.deleted_at is null order by v.created_at desc"
            ).fetchall()]

    def get_video(self, video_id: int) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "select v.*, u.username as created_by_username from videos v left join users u on v.created_by = u.id where v.id = ? and v.deleted_at is null",
                (video_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(video_id)
        return dict(row)
