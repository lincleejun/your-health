"""Tests for ``health.metrics.physiology``."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from health.db.conn import initialize
from health.metrics.physiology import compute_physiology_series


@pytest.fixture
def conn(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    initialize(db_conn)
    return db_conn


def _insert_daily(conn: sqlite3.Connection, day: date, resting_hr: float | None) -> None:
    conn.execute(
        "INSERT INTO daily_summary(date, resting_hr, raw_json) VALUES (?, ?, '{}')",
        (day.isoformat(), resting_hr),
    )


def _insert_hrv(conn: sqlite3.Connection, day: date, weekly_avg: float | None) -> None:
    conn.execute(
        "INSERT INTO hrv(date, weekly_avg, raw_json) VALUES (?, ?, '{}')",
        (day.isoformat(), weekly_avg),
    )


def _insert_sleep(conn: sqlite3.Connection, day: date, total_sleep_s: int | None) -> None:
    conn.execute(
        "INSERT INTO sleep(date, total_sleep_s, raw_json) VALUES (?, ?, '{}')",
        (day.isoformat(), total_sleep_s),
    )


def test_all_none_range_emits_null_points(conn: sqlite3.Connection) -> None:
    start = date(2026, 1, 1)
    end = date(2026, 1, 7)
    series = compute_physiology_series(conn, start=start, end=end)

    assert len(series.resting_hr) == 7
    assert len(series.hrv_weekly_avg) == 7
    assert len(series.sleep_total_hours) == 7

    for tp in series.resting_hr:
        assert tp.value is None
        assert tp.mean_7d is None
        assert tp.mean_28d is None
        assert tp.z_score_28d is None
        assert tp.is_anomaly is False


def test_steady_values_have_zero_z_and_no_anomaly(conn: sqlite3.Connection) -> None:
    start = date(2026, 2, 1)
    # Seed 30 days of identical resting_hr = 50 starting at warm-up.
    for i in range(30):
        _insert_daily(conn, start + timedelta(days=i), 50.0)

    end = start + timedelta(days=29)
    series = compute_physiology_series(conn, start=start, end=end)

    # Look at the last day — full 28d window of identical readings.
    last = series.resting_hr[-1]
    assert last.value == 50.0
    assert last.mean_7d == 50.0
    assert last.mean_28d == 50.0
    assert last.z_score_28d == 0.0
    assert last.is_anomaly is False


def test_sudden_spike_is_flagged(conn: sqlite3.Connection) -> None:
    start = date(2026, 3, 1)
    for i in range(28):
        _insert_daily(conn, start + timedelta(days=i), 50.0)
    spike_day = start + timedelta(days=28)
    _insert_daily(conn, spike_day, 80.0)

    series = compute_physiology_series(conn, start=spike_day, end=spike_day)
    [tp] = series.resting_hr
    assert tp.value == 80.0
    assert tp.z_score_28d is not None
    assert tp.z_score_28d > 1
    assert tp.is_anomaly is True


def test_sparse_data_does_not_divide_by_zero(conn: sqlite3.Connection) -> None:
    start = date(2026, 4, 1)
    end = start + timedelta(days=14)
    # Only 2 days have HRV readings.
    _insert_hrv(conn, start + timedelta(days=3), 60.0)
    _insert_hrv(conn, start + timedelta(days=10), 62.0)

    series = compute_physiology_series(conn, start=start, end=end)
    hrv = series.hrv_weekly_avg
    assert len(hrv) == 15
    # Days without readings have value=None but rolling means may exist after seeded days.
    day3 = hrv[3]
    assert day3.value == 60.0
    # Only one reading in 28d window so mean_28d=None (need >=4).
    assert day3.mean_28d is None
    assert day3.z_score_28d is None
    assert day3.is_anomaly is False

    day10 = hrv[10]
    assert day10.value == 62.0
    # 7d window has only one reading (today) -> need >=2 for mean_7d
    assert day10.mean_7d is None


def test_warm_up_window_is_honoured(conn: sqlite3.Connection) -> None:
    start = date(2026, 5, 1)
    # Seed 28 days BEFORE start.
    for i in range(1, 29):
        _insert_sleep(conn, start - timedelta(days=i), 7 * 3600)
    # And start itself.
    _insert_sleep(conn, start, 7 * 3600)

    series = compute_physiology_series(conn, start=start, end=start)
    [tp] = series.sleep_total_hours
    assert tp.value == 7.0
    # Warm-up worked: first emitted point has a real 28d mean.
    assert tp.mean_28d == 7.0
    assert tp.z_score_28d == 0.0
    assert tp.is_anomaly is False
