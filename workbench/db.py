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


def initialize_db(path: Path, default_user: str = "local-user", default_role: str = "admin") -> None:
    with closing(connect_db(path)) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
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
