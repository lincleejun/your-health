"""Tests for weekly volume and HR zone distribution metrics (metrics-03)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime

import pytest

from health.db.conn import initialize
from health.ingest.models import Activity
from health.ingest.store import upsert_activity
from health.metrics.activity import (
    compute_weekly_volume,
    compute_zone_distribution,
)


@pytest.fixture
def db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    initialize(db_conn)
    return db_conn


def _activity(
    activity_id: int,
    start_ts: datetime,
    sport: str = "running",
    duration_s: float | None = 3600.0,
    distance_m: float | None = 10000.0,
    avg_hr: float | None = 140.0,
) -> Activity:
    return Activity(
        activity_id=activity_id,
        start_ts=start_ts,
        sport=sport,
        duration_s=duration_s,
        distance_m=distance_m,
        avg_hr=avg_hr,
        training_load=None,
        aerobic_te=None,
        anaerobic_te=None,
        raw_json={"activityId": activity_id},
    )


def test_empty_range_returns_empty(db: sqlite3.Connection) -> None:
    weeks = compute_weekly_volume(db, start=date(2026, 5, 1), end=date(2026, 5, 31))
    assert weeks == []
    zd = compute_zone_distribution(
        db, start=date(2026, 5, 1), end=date(2026, 5, 31), max_hr=185, resting_hr=55
    )
    assert zd.total_seconds == 0
    assert zd.zone_seconds == {}


def test_single_sport_week(db: sqlite3.Connection) -> None:
    # 2026-05-04 is a Monday (ISO week 19 of 2026).
    for i, day in enumerate([4, 6, 8]):
        upsert_activity(
            db,
            _activity(
                i + 1,
                datetime(2026, 5, day, 7, 0, tzinfo=UTC),
                duration_s=1800.0,
                distance_m=5000.0,
            ),
        )
    weeks = compute_weekly_volume(db, start=date(2026, 5, 1), end=date(2026, 5, 15))
    assert len(weeks) == 1
    w = weeks[0]
    assert w.week_start == date(2026, 5, 4)
    assert w.total_activities == 3
    assert w.total_distance_km == pytest.approx(15.0)
    assert w.total_duration_h == pytest.approx(1.5)
    assert set(w.by_sport) == {"running"}
    assert w.by_sport["running"].activities == 3


def test_multi_sport_week(db: sqlite3.Connection) -> None:
    upsert_activity(
        db,
        _activity(
            1,
            datetime(2026, 5, 4, 7, 0, tzinfo=UTC),
            sport="running",
            duration_s=3600.0,
            distance_m=10000.0,
        ),
    )
    upsert_activity(
        db,
        _activity(
            2,
            datetime(2026, 5, 5, 7, 0, tzinfo=UTC),
            sport="cycling",
            duration_s=7200.0,
            distance_m=40000.0,
        ),
    )
    weeks = compute_weekly_volume(db, start=date(2026, 5, 1), end=date(2026, 5, 15))
    assert len(weeks) == 1
    w = weeks[0]
    assert set(w.by_sport) == {"running", "cycling"}
    assert w.by_sport["running"].distance_km == pytest.approx(10.0)
    assert w.by_sport["cycling"].distance_km == pytest.approx(40.0)
    assert w.total_distance_km == pytest.approx(50.0)
    assert w.total_duration_h == pytest.approx(3.0)
    assert w.total_activities == 2


def test_cross_week_activity(db: sqlite3.Connection) -> None:
    # Sunday 2026-05-03 is end of ISO week 18; Monday 2026-05-04 starts week 19.
    upsert_activity(db, _activity(1, datetime(2026, 5, 3, 9, 0, tzinfo=UTC)))
    upsert_activity(db, _activity(2, datetime(2026, 5, 4, 9, 0, tzinfo=UTC)))
    weeks = compute_weekly_volume(db, start=date(2026, 4, 27), end=date(2026, 5, 10))
    assert len(weeks) == 2
    assert weeks[0].iso_week == 18
    assert weeks[0].week_start == date(2026, 4, 27)
    assert weeks[1].iso_week == 19
    assert weeks[1].week_start == date(2026, 5, 4)


def test_zone_classification(db: sqlite3.Connection) -> None:
    # max_hr=185, resting_hr=55 → HR-reserve 130.
    # avg_hr=140 → (140-55)/130 ≈ 0.654 → zone 2.
    # avg_hr=160 → (160-55)/130 ≈ 0.808 → zone 4.
    # avg_hr=180 → (180-55)/130 ≈ 0.962 → zone 5.
    upsert_activity(
        db,
        _activity(1, datetime(2026, 5, 4, 7, 0, tzinfo=UTC), avg_hr=140.0, duration_s=1800.0),
    )
    upsert_activity(
        db,
        _activity(2, datetime(2026, 5, 5, 7, 0, tzinfo=UTC), avg_hr=160.0, duration_s=2400.0),
    )
    upsert_activity(
        db,
        _activity(3, datetime(2026, 5, 6, 7, 0, tzinfo=UTC), avg_hr=180.0, duration_s=1200.0),
    )
    zd = compute_zone_distribution(
        db, start=date(2026, 5, 1), end=date(2026, 5, 31), max_hr=185, resting_hr=55
    )
    assert zd.zone_seconds.get(2, 0) == 1800.0
    assert zd.zone_seconds.get(4, 0) == 2400.0
    assert zd.zone_seconds.get(5, 0) == 1200.0
    assert zd.total_seconds == 1800.0 + 2400.0 + 1200.0


def test_zone_null_avg_hr_excluded(db: sqlite3.Connection) -> None:
    upsert_activity(
        db,
        _activity(1, datetime(2026, 5, 4, 7, 0, tzinfo=UTC), avg_hr=None, duration_s=1800.0),
    )
    upsert_activity(
        db,
        _activity(2, datetime(2026, 5, 5, 7, 0, tzinfo=UTC), avg_hr=160.0, duration_s=2400.0),
    )
    zd = compute_zone_distribution(
        db, start=date(2026, 5, 1), end=date(2026, 5, 31), max_hr=185, resting_hr=55
    )
    assert zd.total_seconds == 2400.0
    assert zd.zone_seconds == {4: 2400.0}
