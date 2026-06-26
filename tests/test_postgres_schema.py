from __future__ import annotations

from pathlib import Path


def test_postgres_schema_contains_dbml_core_tables():
    sql = Path("workbench/schema_postgres.sql").read_text(encoding="utf-8").lower()

    for table in [
        "users",
        "projects",
        "project_members",
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
    assert "create extension if not exists pgcrypto" in sql
