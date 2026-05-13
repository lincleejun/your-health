"""Tests for the test harness itself (harness-01)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def test_db_conn_is_in_memory_sqlite(db_conn: sqlite3.Connection) -> None:
    assert isinstance(db_conn, sqlite3.Connection)
    cur = db_conn.execute("SELECT 1 AS one")
    row = cur.fetchone()
    # Row factory should be sqlite3.Row so columns are addressable by name.
    assert row["one"] == 1


def test_db_conn_has_foreign_keys_enabled(db_conn: sqlite3.Connection) -> None:
    (fk,) = db_conn.execute("PRAGMA foreign_keys").fetchone()
    assert fk == 1


def test_db_conn_is_isolated_per_test(db_conn: sqlite3.Connection) -> None:
    db_conn.execute("CREATE TABLE scratch (id INTEGER PRIMARY KEY)")
    db_conn.execute("INSERT INTO scratch DEFAULT VALUES")
    (count,) = db_conn.execute("SELECT COUNT(*) FROM scratch").fetchone()
    assert count == 1


def test_garmin_fixtures_dir_exists() -> None:
    fixtures = Path(__file__).parent / "fixtures" / "garmin"
    assert fixtures.is_dir(), f"expected {fixtures} to exist"
