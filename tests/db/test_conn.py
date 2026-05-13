"""Tests for src/health/db/conn.py."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from health.db.conn import connect, initialize, transaction


def test_connect_creates_file_and_enables_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "health.db"
    conn = connect(db_path)
    try:
        assert db_path.exists()
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1
    finally:
        conn.close()


def test_initialize_creates_schema(tmp_path: Path) -> None:
    conn = connect(tmp_path / "h.db")
    try:
        initialize(conn)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        names = {r["name"] for r in rows}
        expected = {
            "activities",
            "daily_summary",
            "sleep",
            "hrv",
            "body_composition",
            "ingest_runs",
        }
        assert expected.issubset(names)
    finally:
        conn.close()


def test_initialize_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "h.db")
    try:
        initialize(conn)
        initialize(conn)
    finally:
        conn.close()


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    conn = connect(tmp_path / "h.db")
    try:
        initialize(conn)
        with transaction(conn):
            conn.execute(
                "INSERT INTO daily_summary(date, raw_json) VALUES (?, ?)",
                ("2026-05-12", "{}"),
            )
        row = conn.execute(
            "SELECT date FROM daily_summary WHERE date=?", ("2026-05-12",)
        ).fetchone()
        assert row is not None
        assert row["date"] == "2026-05-12"
    finally:
        conn.close()


def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    conn = connect(tmp_path / "h.db")
    try:
        initialize(conn)
        with pytest.raises(RuntimeError), transaction(conn):
            conn.execute(
                "INSERT INTO daily_summary(date, raw_json) VALUES (?, ?)",
                ("2026-05-12", "{}"),
            )
            raise RuntimeError("boom")
        row = conn.execute(
            "SELECT date FROM daily_summary WHERE date=?", ("2026-05-12",)
        ).fetchone()
        assert row is None
    finally:
        conn.close()


def test_connect_returns_row_factory(tmp_path: Path) -> None:
    conn = connect(tmp_path / "h.db")
    try:
        assert conn.row_factory is sqlite3.Row
    finally:
        conn.close()
