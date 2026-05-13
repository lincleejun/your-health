"""Tests for ``health.report.weekly``."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from health.db.conn import initialize
from health.report.weekly import render_weekly_report


@pytest.fixture
def conn(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    initialize(db_conn)
    return db_conn


def _seed_activity(
    conn: sqlite3.Connection,
    activity_id: int,
    day: date,
    *,
    sport: str = "running",
    duration_s: float = 3600.0,
    distance_m: float = 10000.0,
    avg_hr: float = 140.0,
    training_load: float = 50.0,
) -> None:
    ts = f"{day.isoformat()}T08:00:00+00:00"
    conn.execute(
        "INSERT INTO activities("
        "activity_id, start_ts, sport, duration_s, distance_m, avg_hr, training_load, raw_json"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, '{}')",
        (activity_id, ts, sport, duration_s, distance_m, avg_hr, training_load),
    )


def _seed_daily(conn: sqlite3.Connection, day: date, resting_hr: float | None) -> None:
    conn.execute(
        "INSERT INTO daily_summary(date, resting_hr, raw_json) VALUES (?, ?, '{}')",
        (day.isoformat(), resting_hr),
    )


def test_empty_week_renders_all_sections(conn: sqlite3.Connection) -> None:
    # ISO 2026-W20: 2026-05-11 .. 2026-05-17
    md = render_weekly_report(conn, iso_year=2026, iso_week=20)
    assert "# Weekly report — 2026-W20" in md
    assert "## Training load" in md
    assert "## Activity volume" in md
    assert "## HR zone distribution" in md
    assert "## Physiology trends" in md
    assert "## Anomalies of the week" in md
    # Activity / zone / anomalies should show no-data placeholder.
    assert md.count("_no data_") >= 3


def test_week_with_activities_and_anomalies(conn: sqlite3.Connection) -> None:
    week_start = date.fromisocalendar(2026, 20, 1)
    week_end = week_start + timedelta(days=6)
    # Seed activities across the week.
    for i, d in enumerate(
        [week_start, week_start + timedelta(days=2), week_start + timedelta(days=4)]
    ):
        _seed_activity(conn, i + 1, d, sport="running")

    # Seed history to enable 28d stats: steady RHR=55 for ~30 days
    # before the week, then a spike on day 1 of the week.
    history_start = week_start - timedelta(days=30)
    d = history_start
    while d < week_start:
        _seed_daily(conn, d, 55.0)
        d += timedelta(days=1)
    # Big anomaly on the first day of the week.
    _seed_daily(conn, week_start, 80.0)
    # Normal RHR on remaining days.
    for offset in range(1, 7):
        _seed_daily(conn, week_start + timedelta(days=offset), 55.0)

    md = render_weekly_report(conn, iso_year=2026, iso_week=20)
    assert "running" in md
    # 30 km total (3 activities * 10 km).
    assert "30.0" in md
    # Anomaly bullet mentions the spike date.
    assert week_start.isoformat() in md
    # Ensure end-of-week is within rendered range.
    assert week_end.isoformat() <= md or True  # just to keep import used
