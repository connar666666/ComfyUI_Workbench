from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma journal_mode = wal")
    conn.execute("pragma busy_timeout = 5000")
    return conn


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
        conn.commit()
