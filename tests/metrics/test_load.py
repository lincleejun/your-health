"""Tests for the training-load (CTL/ATL/ACWR) metrics."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise

from health.db.conn import initialize
from health.ingest.models import Activity
from health.ingest.store import upsert_activity
from health.metrics.load import LoadPoint, compute_load_series


def _make_activity(
    activity_id: int,
    day: date,
    training_load: float | None,
    *,
    sport: str = "running",
) -> Activity:
    return Activity(
        activity_id=activity_id,
        start_ts=datetime(day.year, day.month, day.day, 12, 0, 0, tzinfo=UTC),
        sport=sport,
        duration_s=3600.0,
        distance_m=10000.0,
        avg_hr=150.0,
        training_load=training_load,
        aerobic_te=3.0,
        anaerobic_te=1.0,
        raw_json={"activityId": activity_id},
    )


def _seed(conn: sqlite3.Connection, acts: list[Activity]) -> None:
    initialize(conn)
    for a in acts:
        upsert_activity(conn, a)
    conn.commit()


def test_empty_range_yields_zero_points(db_conn: sqlite3.Connection) -> None:
    initialize(db_conn)
    start = date(2026, 1, 1)
    end = date(2026, 1, 7)
    points = compute_load_series(db_conn, start=start, end=end)
    assert len(points) == 7
    assert [p.date for p in points] == [start + timedelta(days=i) for i in range(7)]
    for p in points:
        assert p.daily_load == 0.0
        assert p.ctl == 0.0
        assert p.atl == 0.0
        assert p.acwr is None


def test_single_load_spike(db_conn: sqlite3.Connection) -> None:
    start = date(2026, 1, 1)
    end = date(2026, 1, 5)
    # Spike on day 1 only.
    _seed(db_conn, [_make_activity(1, start, 100.0)])
    points = compute_load_series(db_conn, start=start, end=end)
    assert len(points) == 5
    day1 = points[0]
    # CTL_1 = 0 + (100 - 0)/42 ≈ 2.381
    # ATL_1 = 0 + (100 - 0)/7 ≈ 14.286
    assert abs(day1.ctl - 100.0 / 42.0) < 1e-9
    assert abs(day1.atl - 100.0 / 7.0) < 1e-9
    assert day1.daily_load == 100.0
    assert day1.acwr is not None
    assert day1.acwr > 1.0
    # Subsequent days decay (no further load).
    for prev, cur in pairwise(points):
        assert cur.ctl < prev.ctl  # decays
        assert cur.atl < prev.atl


def test_steady_load_converges(db_conn: sqlite3.Connection) -> None:
    start = date(2026, 1, 1)
    end = start + timedelta(days=299)  # 300 days inclusive
    acts = [_make_activity(i + 1, start + timedelta(days=i), 50.0) for i in range(300)]
    _seed(db_conn, acts)
    points = compute_load_series(db_conn, start=start, end=end)
    assert len(points) == 300
    last = points[-1]
    # After ~300 days of constant 50 (≫ 42d time constant) both EWMAs are
    # within fractions of 50 and ACWR sits very close to 1.0.
    assert abs(last.ctl - 50.0) < 0.1
    assert abs(last.atl - 50.0) < 0.1
    assert last.acwr is not None
    assert abs(last.acwr - 1.0) < 0.01


def test_warm_up_window_honoured(db_conn: sqlite3.Connection) -> None:
    start = date(2026, 2, 1)
    end = date(2026, 2, 7)
    # Activities 30 days before the requested start.
    pre_days = [start - timedelta(days=30 - i) for i in range(20)]
    acts = [_make_activity(i + 1, d, 60.0) for i, d in enumerate(pre_days)]
    _seed(db_conn, acts)
    points = compute_load_series(db_conn, start=start, end=end)
    assert len(points) == 7
    # Warm-up should have raised CTL above 0 even though no activity falls in [start, end].
    assert points[0].ctl > 0.0
    assert points[0].atl >= 0.0
    assert points[0].daily_load == 0.0


def test_null_training_load_is_zero(db_conn: sqlite3.Connection) -> None:
    start = date(2026, 3, 1)
    end = date(2026, 3, 3)
    _seed(
        db_conn,
        [
            _make_activity(1, start, None),
            _make_activity(2, start + timedelta(days=1), None),
        ],
    )
    points = compute_load_series(db_conn, start=start, end=end)
    assert len(points) == 3
    for p in points:
        assert p.daily_load == 0.0
        assert p.ctl == 0.0
        assert p.atl == 0.0
        assert p.acwr is None
    # Sanity: LoadPoint is frozen dataclass.
    assert isinstance(points[0], LoadPoint)
