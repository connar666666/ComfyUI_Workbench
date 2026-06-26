from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg.rows import dict_row


SCHEMA_PATH = Path(__file__).with_name("schema_postgres.sql")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_params(params: Any | None) -> Any:
    if params is None:
        return None
    if isinstance(params, tuple):
        return tuple(str(item) if hasattr(item, "hex") and item.__class__.__name__ == "UUID" else item for item in params)
    if isinstance(params, list):
        return [str(item) if hasattr(item, "hex") and item.__class__.__name__ == "UUID" else item for item in params]
    return params


def _normalize_value(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _normalize_row(row):
    if row is None:
        return None
    return {key: _normalize_value(value) for key, value in row.items()}


def _translate_sql(sql: str) -> str:
    translated = sql
    translated = translated.replace("?", "%s")
    translated = re.sub(r"\bcollate\s+nocase\b", "", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bis_revoked\s*=\s*0\b", "is_revoked = false", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\bis_revoked\s*=\s*1\b", "is_revoked = true", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\benabled\s*=\s*1\b", "enabled = true", translated, flags=re.IGNORECASE)
    translated = re.sub(r"\benabled\s*=\s*0\b", "enabled = false", translated, flags=re.IGNORECASE)
    return translated


def _needs_returning_id(sql: str) -> bool:
    lowered = sql.strip().lower()
    return lowered.startswith("insert into") and " returning " not in lowered


class PgCursorAdapter:
    def __init__(self, cursor: psycopg.Cursor):
        self._cursor = cursor
        self.lastrowid: str | None = None

    def execute(self, sql: str, params: Any | None = None) -> "PgCursorAdapter":
        translated = _translate_sql(sql)
        fetch_insert_id = _needs_returning_id(translated)
        if fetch_insert_id:
            translated = translated.rstrip().rstrip(";") + " returning id"
        self._cursor.execute(translated, _normalize_params(params))
        if fetch_insert_id:
            row = self._cursor.fetchone()
            normalized = _normalize_row(row)
            self.lastrowid = normalized["id"] if normalized is not None else None
        return self

    def fetchone(self):
        return _normalize_row(self._cursor.fetchone())

    def fetchall(self):
        return [_normalize_row(row) for row in self._cursor.fetchall()]


class WorkbenchConnection:
    def __init__(self, database_url: str):
        self._conn = psycopg.connect(database_url, row_factory=dict_row)

    def __enter__(self) -> "WorkbenchConnection":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        if exc_type is not None:
            self._conn.rollback()
        self.close()
        return False

    def execute(self, sql: str, params: Any | None = None) -> PgCursorAdapter:
        cursor = self._conn.cursor()
        return PgCursorAdapter(cursor).execute(sql, params)

    def executescript(self, sql: str) -> None:
        self._conn.execute(sql)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def database_url_for_schema(database_url: str, schema: str) -> str:
    split = urlsplit(database_url)
    options = f"options={quote(f'-csearch_path={schema},public')}"
    query = f"{split.query}&{options}" if split.query else options
    return urlunsplit((split.scheme, split.netloc, split.path, query, split.fragment))


def connect_db(database_url: str | Path) -> WorkbenchConnection:
    return WorkbenchConnection(str(database_url))


def initialize_db(
    database_url: str | Path,
    default_user: str = "local-user",
    default_role: str = "admin",
    schema: str | None = None,
) -> None:
    target_url = str(database_url)
    if schema:
        with connect_db(target_url) as conn:
            conn.execute(f"create schema if not exists {schema}")
            conn.commit()
        target_url = database_url_for_schema(target_url, schema)

    with connect_db(target_url) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        now = utc_now()
        conn.execute(
            """
            insert into users(username, display_name, role, status, created_at, updated_at)
            values (%s, %s, %s, 'ACTIVE', %s, %s)
            on conflict(username) do update set role = excluded.role, updated_at = excluded.updated_at
            returning id
            """,
            (default_user, default_user, default_role, now, now),
        )
        conn.commit()
