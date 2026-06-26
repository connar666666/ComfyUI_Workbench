from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class WorkbenchConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        super().__exit__(exc_type, exc_value, traceback)
        self.close()
        return False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, factory=WorkbenchConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma journal_mode = wal")
    conn.execute("pragma busy_timeout = 5000")
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"pragma table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply schema additions that may be missing in existing databases."""
    existing = {row[0] for row in conn.execute("select name from sqlite_master where type='table'").fetchall()}

    # First-time: run full schema
    if "users" not in existing:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        return

    # Migrations for existing databases
    user_cols = {row[1] for row in conn.execute("pragma table_info('users')").fetchall()}
    if "password_hash" not in user_cols:
        conn.execute("alter table users add column password_hash text")
    if "last_seen_at" not in user_cols:
        conn.execute("alter table users add column last_seen_at text")

    if "invite_tokens" not in existing:
        conn.execute("""
            create table if not exists invite_tokens (
              id integer primary key autoincrement,
              token_hash text not null unique,
              created_by integer not null references users(id),
              role text not null check (role in ('member', 'admin')),
              max_uses integer,
              use_count integer not null default 0,
              expires_at text,
              created_at text not null,
              is_revoked integer not null default 0
            )
        """)

    if "projects" not in existing:
        conn.execute("""
            create table if not exists projects (
              id integer primary key autoincrement,
              name text not null,
              description text not null default '',
              created_by integer not null references users(id),
              archived_at text,
              created_at text not null,
              updated_at text not null
            )
        """)

    if "project_members" not in existing:
        conn.execute("""
            create table if not exists project_members (
              project_id integer not null references projects(id) on delete cascade,
              user_id integer not null references users(id) on delete cascade,
              role text not null check (role in ('owner', 'editor', 'viewer')),
              created_at text not null,
              updated_at text not null,
              primary key(project_id, user_id)
            )
        """)

    if "project_workflows" not in existing:
        conn.execute("""
            create table if not exists project_workflows (
              id integer primary key autoincrement,
              project_id integer not null references projects(id) on delete cascade,
              workflow_id text not null,
              display_name text,
              sort_order integer not null default 0,
              defaults_json text not null default '{}',
              enabled integer not null default 1,
              created_by integer references users(id),
              created_at text not null,
              updated_at text not null,
              unique(project_id, workflow_id)
            )
        """)

    if "remote_workflow_runs" not in existing:
        conn.execute("""
            create table if not exists remote_workflow_runs (
              id integer primary key autoincrement,
              project_id integer not null references projects(id),
              project_workflow_id integer references project_workflows(id),
              workflow_id text not null,
              prompt_id text unique,
              status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled')),
              input_values_json text not null default '{}',
              results_json text not null default '[]',
              saved_asset_ids_json text not null default '[]',
              error_message text,
              created_by integer references users(id),
              created_at text not null,
              updated_at text not null,
              completed_at text
            )
        """)

    if "assets" in existing and not _column_exists(conn, "assets", "project_id"):
        conn.execute("alter table assets add column project_id integer references projects(id)")

    for column, sql in [
        ("project_id", "alter table generation_jobs add column project_id integer references projects(id)"),
        ("canvas_id", "alter table generation_jobs add column canvas_id text"),
        ("canvas_node_id", "alter table generation_jobs add column canvas_node_id text"),
        ("canvas_version_id", "alter table generation_jobs add column canvas_version_id integer"),
    ]:
        if "generation_jobs" in existing and not _column_exists(conn, "generation_jobs", column):
            conn.execute(sql)

    if "node_versions" not in existing:
        conn.execute("""
            create table if not exists node_versions (
              id integer primary key autoincrement,
              canvas_id text not null,
              node_id text not null,
              generation_job_id integer not null references generation_jobs(id),
              output_video_id integer references videos(id),
              version_number integer not null,
              parent_version_id integer references node_versions(id),
              prompt text not null,
              negative_prompt text,
              input_asset_ids_json text not null default '[]',
              params_json text not null default '{}',
              snapshot_json text not null default '{}',
              status text not null check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled')),
              created_by integer references users(id),
              created_at text not null,
              unique(canvas_id, node_id, version_number)
            )
        """)


def _ensure_legacy_project(conn: sqlite3.Connection, default_user: str) -> None:
    tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'").fetchall()}
    if not {"projects", "project_members"}.issubset(tables):
        return
    if "assets" not in tables and "generation_jobs" not in tables:
        return

    has_unscoped_assets = (
        "assets" in tables
        and any(row["name"] == "project_id" for row in conn.execute("pragma table_info('assets')").fetchall())
        and conn.execute("select count(*) as count from assets where project_id is null").fetchone()["count"] > 0
    )
    has_unscoped_jobs = (
        "generation_jobs" in tables
        and any(row["name"] == "project_id" for row in conn.execute("pragma table_info('generation_jobs')").fetchall())
        and conn.execute("select count(*) as count from generation_jobs where project_id is null").fetchone()["count"] > 0
    )
    if not has_unscoped_assets and not has_unscoped_jobs:
        return

    user = conn.execute("select id from users where username = ?", (default_user,)).fetchone()
    if user is None:
        user = conn.execute("select id from users order by id limit 1").fetchone()
    if user is None:
        return

    now = utc_now()
    project = conn.execute("select id from projects where name = 'Legacy Workspace' order by id limit 1").fetchone()
    if project is None:
        cur = conn.execute(
            """
            insert into projects(name, description, created_by, created_at, updated_at)
            values ('Legacy Workspace', 'Migrated global assets and jobs', ?, ?, ?)
            """,
            (user["id"], now, now),
        )
        project_id = cur.lastrowid
    else:
        project_id = project["id"]

    conn.execute(
        """
        insert into project_members(project_id, user_id, role, created_at, updated_at)
        values (?, ?, 'owner', ?, ?)
        on conflict(project_id, user_id) do nothing
        """,
        (project_id, user["id"], now, now),
    )
    if has_unscoped_assets:
        conn.execute("update assets set project_id = ? where project_id is null", (project_id,))
    if has_unscoped_jobs:
        conn.execute("update generation_jobs set project_id = ? where project_id is null", (project_id,))


def initialize_db(path: Path, default_user: str = "local-user", default_role: str = "admin") -> None:
    with closing(connect_db(path)) as conn:
        _run_migrations(conn)
        now = utc_now()
        conn.execute(
            """
            insert into users(username, display_name, role, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            on conflict(username) do update set role = excluded.role, updated_at = excluded.updated_at
            """,
            (default_user, default_user, default_role, now, now),
        )
        _ensure_legacy_project(conn, default_user)
        conn.commit()
