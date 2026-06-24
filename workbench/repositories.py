from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .db import connect_db, utc_now
from .errors import NotFoundError


class WorkbenchRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def get_user_by_username(self, username: str) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from users where username = ?", (username,)).fetchone()
        if row is None:
            raise NotFoundError(username)
        return dict(row)

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

    def list_assets(self, kind: str | None = None) -> list[dict[str, Any]]:
        sql = "select * from assets where deleted_at is null"
        params: list[Any] = []
        if kind:
            sql += " and kind = ?"
            params.append(kind)
        sql += " order by created_at desc, id desc"
        with connect_db(self.db_path) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

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
    ) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cur = conn.execute(
                """
                insert into generation_jobs(
                  created_by, status, prompt, duration_sec, resolution, audio_start_sec,
                  reference_image_asset_id, reference_audio_asset_id, replace_audio_asset_id,
                  created_at, updated_at
                )
                values (?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    now,
                    now,
                ),
            )
            job_id = cur.lastrowid
            for asset_id, role in [
                (reference_image_asset_id, "reference_image"),
                (reference_audio_asset_id, "reference_audio"),
                (replace_audio_asset_id, "replace_audio"),
            ]:
                if asset_id is not None:
                    conn.execute(
                        "insert into job_inputs(job_id, asset_id, role, created_at) values (?, ?, ?, ?)",
                        (job_id, asset_id, role, now),
                    )
            conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: int) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from generation_jobs where id = ?", (job_id,)).fetchone()
        if row is None:
            raise NotFoundError(job_id)
        return dict(row)

    def list_jobs(self) -> list[dict[str, Any]]:
        with connect_db(self.db_path) as conn:
            return [dict(row) for row in conn.execute("select * from generation_jobs order by created_at desc, id desc").fetchall()]

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

    def cancel_job(self, job_id: int) -> None:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update generation_jobs set status = 'canceled', completed_at = ?, updated_at = ? where id = ? and status = 'queued'",
                (now, now, job_id),
            )
            conn.commit()
