from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import sqlite3

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

    # ── Projects ───────────────────────────────────────────────────────

    def create_project(
        self,
        *,
        name: str,
        description: str,
        created_by: int,
    ) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cur = conn.execute(
                """
                insert into projects(name, description, created_by, created_at, updated_at)
                values (?, ?, ?, ?, ?)
                """,
                (name, description, created_by, now, now),
            )
            project_id = cur.lastrowid
            conn.execute(
                """
                insert into project_members(project_id, user_id, role, created_at, updated_at)
                values (?, ?, 'owner', ?, ?)
                """,
                (project_id, created_by, now, now),
            )
            conn.commit()
        return self.get_project(project_id)

    def get_project(self, project_id: int) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from projects where id = ? and archived_at is null", (project_id,)).fetchone()
        if row is None:
            raise NotFoundError(project_id)
        return dict(row)

    def list_projects(self, *, user_id: int, role: str) -> list[dict[str, Any]]:
        if role == "admin":
            sql = """
                select p.*,
                       pm.role as current_user_role,
                       (select count(*) from project_members m where m.project_id = p.id) as member_count
                from projects p
                left join project_members pm on pm.project_id = p.id and pm.user_id = ?
                where p.archived_at is null
                order by p.updated_at desc, p.id desc
            """
            params: list[Any] = [user_id]
        else:
            sql = """
                select p.*, pm.role as current_user_role,
                       (select count(*) from project_members m where m.project_id = p.id) as member_count
                from projects p
                join project_members pm on pm.project_id = p.id and pm.user_id = ?
                where p.archived_at is null
                order by p.updated_at desc, p.id desc
            """
            params = [user_id]
        with connect_db(self.db_path) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def get_project_member(self, project_id: int, user_id: int) -> dict[str, Any] | None:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                """
                select pm.*, u.username, u.display_name
                from project_members pm
                join users u on u.id = pm.user_id
                where pm.project_id = ? and pm.user_id = ?
                """,
                (project_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def list_project_members(self, project_id: int) -> list[dict[str, Any]]:
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                """
                select pm.project_id, pm.user_id, pm.role, pm.created_at, pm.updated_at,
                       u.username, u.display_name
                from project_members pm
                join users u on u.id = pm.user_id
                where pm.project_id = ?
                order by case pm.role when 'owner' then 0 when 'editor' then 1 else 2 end, u.username
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_project_member(self, *, project_id: int, user_id: int, role: str) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                insert into project_members(project_id, user_id, role, created_at, updated_at)
                values (?, ?, ?, ?, ?)
                on conflict(project_id, user_id) do update set
                  role = excluded.role,
                  updated_at = excluded.updated_at
                """,
                (project_id, user_id, role, now, now),
            )
            conn.execute("update projects set updated_at = ? where id = ?", (now, project_id))
            conn.commit()
        member = self.get_project_member(project_id, user_id)
        if member is None:
            raise NotFoundError(user_id)
        return member

    def remove_project_member(self, *, project_id: int, user_id: int) -> None:
        with connect_db(self.db_path) as conn:
            member = conn.execute(
                "select role from project_members where project_id = ? and user_id = ?",
                (project_id, user_id),
            ).fetchone()
            if member is None:
                raise NotFoundError(user_id)
            if member["role"] == "owner":
                owner_count = conn.execute(
                    "select count(*) as count from project_members where project_id = ? and role = 'owner'",
                    (project_id,),
                ).fetchone()["count"]
                if owner_count <= 1:
                    raise ConflictError("project must keep at least one owner")
            conn.execute("delete from project_members where project_id = ? and user_id = ?", (project_id, user_id))
            conn.commit()

    # ── Folders ────────────────────────────────────────────────────────

    def create_folder(
        self,
        *,
        scope: str,
        name: str,
        parent_id: int | None,
        created_by: int | None,
    ) -> int:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cur = conn.execute(
                """
                insert into folders(parent_id, scope, name, created_by, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?)
                """,
                (parent_id, scope, name, created_by, now, now),
            )
            conn.commit()
            return cur.lastrowid

    def get_folder(self, folder_id: int) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                """
                select f.*, coalesce(cnt.c, 0) as asset_count
                from folders f
                left join (
                    select folder_id, count(*) as c
                    from assets
                    where deleted_at is null and folder_id is not null
                    group by folder_id
                ) cnt on cnt.folder_id = f.id
                where f.id = ?
                """,
                (folder_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(folder_id)
        return dict(row)

    def list_folders(
        self,
        *,
        scope: str,
        parent_id: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = """
            select f.*, coalesce(cnt.c, 0) as asset_count
            from folders f
            left join (
                select folder_id, count(*) as c
                from assets
                where deleted_at is null and folder_id is not null
                group by folder_id
            ) cnt on cnt.folder_id = f.id
            where f.scope = ?
        """
        params: list[Any] = [scope]
        if parent_id is None:
            sql += " and f.parent_id is null"
        else:
            sql += " and f.parent_id = ?"
            params.append(parent_id)
        sql += " order by f.name collate nocase asc, f.id asc"
        with connect_db(self.db_path) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def rename_folder(self, folder_id: int, name: str) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update folders set name = ?, updated_at = ? where id = ?",
                (name, now, folder_id),
            )
            conn.commit()
        return self.get_folder(folder_id)

    def delete_folder(self, folder_id: int) -> None:
        with connect_db(self.db_path) as conn:
            conn.execute("delete from folders where id = ?", (folder_id,))
            conn.commit()

    def count_assets_in_folder(self, folder_id: int) -> int:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "select count(*) as c from assets where folder_id = ? and deleted_at is null",
                (folder_id,),
            ).fetchone()
        return int(row["c"])

    def count_child_folders(self, folder_id: int) -> int:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "select count(*) as c from folders where parent_id = ?",
                (folder_id,),
            ).fetchone()
        return int(row["c"])

    def find_folder_by_name(
        self,
        *,
        scope: str,
        name: str,
        parent_id: int | None,
        exclude_id: int | None = None,
    ) -> dict[str, Any] | None:
        sql = "select * from folders where scope = ? and name = ?"
        params: list[Any] = [scope, name]
        if parent_id is None:
            sql += " and parent_id is null"
        else:
            sql += " and parent_id = ?"
            params.append(parent_id)
        if exclude_id is not None:
            sql += " and id != ?"
            params.append(exclude_id)
        with connect_db(self.db_path) as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

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
        project_id: int | None = None,
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
                insert into assets(project_id, folder_id, kind, original_filename, storage_key, mime_type,
                                   size_bytes, sha256, uploaded_by, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, folder_id, kind, original_filename, storage_key, mime_type, size_bytes, sha256, uploaded_by, now, now),
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
        project_id: int | None = None,
        folder_id: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = "select a.*, u.username as uploaded_by_username from assets a left join users u on a.uploaded_by = u.id where a.deleted_at is null"
        params: list[Any] = []
        if project_id is not None:
            sql += " and a.project_id = ?"
            params.append(project_id)
        if kind:
            sql += " and a.kind = ?"
            params.append(kind)
        if folder_id is not None:
            sql += " and a.folder_id = ?"
            params.append(folder_id)
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
        project_id: int | None = None,
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
                  project_id, created_by, status, prompt, duration_sec, resolution, audio_start_sec,
                  reference_image_asset_id, reference_audio_asset_id, replace_audio_asset_id,
                  canvas_id, canvas_node_id, canvas_version_id, created_at, updated_at
                )
                values (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
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
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = "select j.*, u.username as created_by_username from generation_jobs j left join users u on j.created_by = u.id"
        params: list[Any] = []
        conditions: list[str] = []
        if project_id is not None:
            conditions.append("j.project_id = ?")
            params.append(project_id)
        if role != "admin" and user_id is not None:
            conditions.append("j.created_by = ?")
            params.append(user_id)
        if conditions:
            sql += " where " + " and ".join(conditions)
        sql += " order by j.created_at desc, j.id desc"
        with connect_db(self.db_path) as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    # ── Project Workflows ──────────────────────────────────────────────

    def create_project_workflow(
        self,
        *,
        project_id: int,
        workflow_id: str,
        display_name: str | None,
        defaults: dict[str, Any],
        created_by: int,
    ) -> dict[str, Any]:
        now = utc_now()
        defaults_json = json.dumps(defaults, ensure_ascii=False)
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                "select coalesce(max(sort_order), -1) + 1 as next_order from project_workflows where project_id = ?",
                (project_id,),
            ).fetchone()
            cur = conn.execute(
                """
                insert into project_workflows(project_id, workflow_id, display_name, sort_order, defaults_json, enabled, created_by, created_at, updated_at)
                values (?, ?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (project_id, workflow_id, display_name, row["next_order"], defaults_json, created_by, now, now),
            )
            conn.commit()
        return self.get_project_workflow(cur.lastrowid)

    def get_project_workflow(self, project_workflow_id: int) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute("select * from project_workflows where id = ?", (project_workflow_id,)).fetchone()
        if row is None:
            raise NotFoundError(project_workflow_id)
        return self._decode_project_workflow(dict(row))

    def list_project_workflows(self, project_id: int) -> list[dict[str, Any]]:
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                "select * from project_workflows where project_id = ? order by sort_order asc, id asc",
                (project_id,),
            ).fetchall()
        return [self._decode_project_workflow(dict(row)) for row in rows]

    def create_remote_workflow_run(
        self,
        *,
        project_id: int,
        project_workflow_id: int,
        workflow_id: str,
        input_values: dict[str, Any],
        created_by: int,
    ) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            cur = conn.execute(
                """
                insert into remote_workflow_runs(
                  project_id, project_workflow_id, workflow_id, status,
                  input_values_json, created_by, created_at, updated_at
                )
                values (?, ?, ?, 'queued', ?, ?, ?, ?)
                """,
                (project_id, project_workflow_id, workflow_id, json.dumps(input_values, ensure_ascii=False), created_by, now, now),
            )
            conn.commit()
        return self.get_remote_workflow_run(cur.lastrowid)

    def mark_remote_workflow_run_started(self, run_id: int, prompt_id: str) -> dict[str, Any]:
        now = utc_now()
        with connect_db(self.db_path) as conn:
            conn.execute(
                "update remote_workflow_runs set status = 'running', prompt_id = ?, updated_at = ? where id = ?",
                (prompt_id, now, run_id),
            )
            conn.commit()
        return self.get_remote_workflow_run(run_id)

    def update_remote_workflow_run_result(
        self,
        *,
        run_id: int,
        status: str,
        results: list[dict[str, Any]],
        saved_asset_ids: list[int] | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        completed_at = now if status in {"succeeded", "failed", "canceled"} else None
        with connect_db(self.db_path) as conn:
            conn.execute(
                """
                update remote_workflow_runs
                set status = ?, results_json = ?, saved_asset_ids_json = ?, error_message = ?,
                    completed_at = coalesce(?, completed_at), updated_at = ?
                where id = ?
                """,
                (
                    status,
                    json.dumps(results, ensure_ascii=False),
                    json.dumps(saved_asset_ids or [], ensure_ascii=False),
                    error_message,
                    completed_at,
                    now,
                    run_id,
                ),
            )
            conn.commit()
        return self.get_remote_workflow_run(run_id)

    def get_remote_workflow_run(self, run_id: int) -> dict[str, Any]:
        with connect_db(self.db_path) as conn:
            row = conn.execute(
                """
                select r.*, pw.display_name as project_workflow_display_name
                from remote_workflow_runs r
                left join project_workflows pw on pw.id = r.project_workflow_id
                where r.id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(run_id)
        return self._decode_remote_workflow_run(dict(row))

    def list_remote_workflow_runs(self, project_id: int) -> list[dict[str, Any]]:
        with connect_db(self.db_path) as conn:
            rows = conn.execute(
                """
                select r.*, pw.display_name as project_workflow_display_name, u.username as created_by_username
                from remote_workflow_runs r
                left join project_workflows pw on pw.id = r.project_workflow_id
                left join users u on u.id = r.created_by
                where r.project_id = ?
                order by r.created_at desc, r.id desc
                """,
                (project_id,),
            ).fetchall()
        return [self._decode_remote_workflow_run(dict(row)) for row in rows]

    def list_project_history(self, project_id: int) -> list[dict[str, Any]]:
        local_items = [
            {
                "id": row["id"],
                "type": "local_generation",
                "status": row["status"],
                "title": row["prompt"],
                "created_by": row["created_by"],
                "created_by_username": row.get("created_by_username"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "completed_at": row.get("completed_at"),
                "input_summary": {"prompt": row["prompt"], "resolution": row["resolution"], "duration_sec": row["duration_sec"]},
                "asset_ids": [
                    asset_id
                    for asset_id in [
                        row.get("reference_image_asset_id"),
                        row.get("reference_audio_asset_id"),
                        row.get("replace_audio_asset_id"),
                    ]
                    if asset_id is not None
                ],
                "result_asset_ids": [],
                "remote_results": [],
                "error_message": row.get("error_message"),
            }
            for row in self.list_jobs(project_id=project_id, role="admin")
        ]
        remote_items = [
            {
                "id": row["id"],
                "type": "remote_workflow",
                "status": row["status"],
                "title": row.get("project_workflow_display_name") or row["workflow_id"],
                "created_by": row["created_by"],
                "created_by_username": row.get("created_by_username"),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "completed_at": row.get("completed_at"),
                "input_summary": row["input_values"],
                "asset_ids": [],
                "result_asset_ids": row["saved_asset_ids"],
                "remote_results": row["results"],
                "error_message": row.get("error_message"),
            }
            for row in self.list_remote_workflow_runs(project_id)
        ]
        return sorted(local_items + remote_items, key=lambda item: (item["created_at"], item["id"]), reverse=True)

    @staticmethod
    def _decode_project_workflow(row: dict[str, Any]) -> dict[str, Any]:
        row["defaults"] = json.loads(row.pop("defaults_json") or "{}")
        row["enabled"] = bool(row["enabled"])
        return row

    @staticmethod
    def _decode_remote_workflow_run(row: dict[str, Any]) -> dict[str, Any]:
        row["input_values"] = json.loads(row.pop("input_values_json") or "{}")
        row["results"] = json.loads(row.pop("results_json") or "[]")
        row["saved_asset_ids"] = json.loads(row.pop("saved_asset_ids_json") or "[]")
        return row

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
