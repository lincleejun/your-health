"""Schema integrity tests for src/health/db/schema.sql."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

SCHEMA_PATH = Path("src/health/db/schema.sql")

EXPECTED_TABLES = {
    "activities",
    "daily_summary",
    "sleep",
    "hrv",
    "body_composition",
    "ingest_runs",
}

EXPECTED_COLUMNS: dict[str, set[str]] = {
    "activities": {
        "activity_id",
        "start_ts",
        "sport",
        "duration_s",
        "distance_m",
        "avg_hr",
        "training_load",
        "aerobic_te",
        "anaerobic_te",
        "raw_json",
    },
    "daily_summary": {
        "date",
        "steps",
        "resting_hr",
        "body_battery_min",
        "body_battery_max",
        "stress_avg",
        "calories_active",
        "raw_json",
    },
    "sleep": {
        "date",
        "total_sleep_s",
        "deep_s",
        "light_s",
        "rem_s",
        "awake_s",
        "sleep_score",
        "raw_json",
    },
    "hrv": {"date", "weekly_avg", "last_night_avg", "status", "raw_json"},
    "body_composition": {
        "date",
        "weight_kg",
        "body_fat_pct",
        "muscle_mass_kg",
        "raw_json",
    },
    "ingest_runs": {
        "id",
        "started_at",
        "finished_at",
        "days_requested",
        "rows_written",
        "error",
    },
}


@pytest.fixture
def schema_sql() -> str:
    assert SCHEMA_PATH.exists(), f"missing {SCHEMA_PATH}"
    return SCHEMA_PATH.read_text()


def _apply(conn: sqlite3.Connection, sql: str) -> None:
    conn.executescript(sql)


def test_schema_creates_all_tables(db_conn: sqlite3.Connection, schema_sql: str) -> None:
    _apply(db_conn, schema_sql)
    rows = db_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert EXPECTED_TABLES.issubset(names), f"missing tables: {EXPECTED_TABLES - names}"


def test_schema_columns(db_conn: sqlite3.Connection, schema_sql: str) -> None:
    _apply(db_conn, schema_sql)
    for table, expected in EXPECTED_COLUMNS.items():
        cols = {row["name"] for row in db_conn.execute(f"PRAGMA table_info({table})").fetchall()}
        missing = expected - cols
        assert not missing, f"{table} missing columns: {missing}"


def test_schema_has_indices(db_conn: sqlite3.Connection, schema_sql: str) -> None:
    _apply(db_conn, schema_sql)
    rows = db_conn.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    indexed_tables = {r["tbl_name"] for r in rows}
    # activities indexed on start_ts; date-keyed tables already have implicit PK index,
    # but spec calls for explicit index on date columns too.
    assert "activities" in indexed_tables, "expected an index on activities"


def test_schema_is_idempotent(db_conn: sqlite3.Connection, schema_sql: str) -> None:
    _apply(db_conn, schema_sql)
    _apply(db_conn, schema_sql)


def test_activity_id_is_primary_key(db_conn: sqlite3.Connection, schema_sql: str) -> None:
    _apply(db_conn, schema_sql)
    info = db_conn.execute("PRAGMA table_info(activities)").fetchall()
    pk_cols = [r["name"] for r in info if r["pk"] > 0]
    assert pk_cols == ["activity_id"]
