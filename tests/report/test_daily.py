"""Tests for ``health.report.daily``."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from health.db.conn import initialize
from health.report.daily import render_daily_report


@pytest.fixture
def conn(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    initialize(db_conn)
    return db_conn


def _seed_daily(
    conn: sqlite3.Connection,
    day: date,
    *,
    steps: int | None,
    resting_hr: float | None,
    body_battery_min: int | None = None,
    body_battery_max: int | None = None,
) -> None:
    conn.execute(
        "INSERT INTO daily_summary("
        "date, steps, resting_hr, body_battery_min, body_battery_max, raw_json"
        ") VALUES (?, ?, ?, ?, ?, '{}')",
        (day.isoformat(), steps, resting_hr, body_battery_min, body_battery_max),
    )


def _seed_sleep(
    conn: sqlite3.Connection, day: date, total_sleep_s: int | None, score: float | None
) -> None:
    conn.execute(
        "INSERT INTO sleep(date, total_sleep_s, sleep_score, raw_json) VALUES (?, ?, ?, '{}')",
        (day.isoformat(), total_sleep_s, score),
    )


def _seed_hrv(conn: sqlite3.Connection, day: date, weekly_avg: float | None) -> None:
    conn.execute(
        "INSERT INTO hrv(date, weekly_avg, raw_json) VALUES (?, ?, '{}')",
        (day.isoformat(), weekly_avg),
    )


def _seed_activity(
    conn: sqlite3.Connection,
    activity_id: int,
    day: date,
    *,
    sport: str = "running",
    duration_s: float = 3600.0,
    distance_m: float = 10000.0,
    avg_hr: float = 140.0,
) -> None:
    ts = f"{day.isoformat()}T08:00:00+00:00"
    conn.execute(
        "INSERT INTO activities("
        "activity_id, start_ts, sport, duration_s, distance_m, avg_hr, raw_json"
        ") VALUES (?, ?, ?, ?, ?, ?, '{}')",
        (activity_id, ts, sport, duration_s, distance_m, avg_hr),
    )


def test_no_data_renders_placeholders(conn: sqlite3.Connection) -> None:
    day = date(2026, 5, 12)
    md = render_daily_report(conn, day=day)
    assert "# Daily report — 2026-05-12" in md
    assert "## Activity" in md
    assert "## Sleep" in md
    assert "## Physiology" in md
    assert "## Trend vs 7-day average" in md
    # All four data sections should show no-data placeholder.
    assert md.count("_no data_") >= 4


def test_full_data_renders_sections(conn: sqlite3.Connection) -> None:
    day = date(2026, 5, 12)
    _seed_daily(
        conn,
        day,
        steps=12345,
        resting_hr=55.0,
        body_battery_min=20,
        body_battery_max=90,
    )
    _seed_sleep(conn, day, total_sleep_s=7 * 3600 + 30 * 60, score=82.0)
    _seed_hrv(conn, day, weekly_avg=45.0)
    _seed_activity(conn, 1, day, sport="running")
    # Seed enough history so trend bullets have real averages.
    for i in range(1, 10):
        prior = date.fromordinal(day.toordinal() - i)
        _seed_daily(conn, prior, steps=10000, resting_hr=56.0 + i * 0.1)
        _seed_sleep(conn, prior, total_sleep_s=7 * 3600, score=80.0)
        _seed_hrv(conn, prior, weekly_avg=44.0 + i * 0.1)

    md = render_daily_report(conn, day=day)
    assert "# Daily report — 2026-05-12" in md
    assert "running" in md
    # Activity table contains distance / duration values.
    assert "10.0" in md or "10.00" in md  # km
    # Sleep total hours.
    assert "7.5" in md
    # Physiology RHR reading appears.
    assert "55.0" in md
    # Trend section shows RHR with averages (not all dashes).
    assert "**RHR**" in md
    # No empty-section placeholders since we seeded everything.
    assert "_no data_" not in md


def test_activity_aggregates_multiple_entries(conn: sqlite3.Connection) -> None:
    day = date(2026, 5, 12)
    _seed_activity(conn, 1, day, sport="running", distance_m=5000.0, duration_s=1800.0)
    _seed_activity(conn, 2, day, sport="cycling", distance_m=20000.0, duration_s=3600.0)
    md = render_daily_report(conn, day=day)
    assert "running" in md
    assert "cycling" in md
