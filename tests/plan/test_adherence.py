"""Tests for weekly plan-adherence scoring."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest

from health.db.conn import initialize
from health.plan.adherence import score_week
from health.plan.schema import Plan

# An ISO week with a Monday on a known date.
# 2026-W20 starts Monday 2026-05-11.
ISO_YEAR = 2026
ISO_WEEK = 20
MONDAY = date(2026, 5, 11)


def _full_plan() -> Plan:
    return Plan.model_validate(
        {
            "athlete": {"name": "X", "resting_hr": 55, "max_hr": 185},
            "weekly_targets": {
                "runs": 3,
                "run_distance_km": 25,
                "strength_sessions": 1,
                "long_run_km": 10,
                "sleep_hours_avg": 7.5,
                "weekly_load_target": 350,
            },
        }
    )


def _iso_ts(day_offset: int, hour: int = 7) -> str:
    dt = datetime(MONDAY.year, MONDAY.month, MONDAY.day, hour, 0, tzinfo=UTC) + timedelta(
        days=day_offset
    )
    return dt.isoformat()


def _insert_activity(
    conn: sqlite3.Connection,
    *,
    activity_id: int,
    day_offset: int,
    sport: str,
    distance_m: float = 0.0,
    training_load: float | None = None,
) -> None:
    conn.execute(
        "INSERT INTO activities (activity_id, start_ts, sport, distance_m,"
        " training_load, raw_json) VALUES (?, ?, ?, ?, ?, '{}')",
        (activity_id, _iso_ts(day_offset), sport, distance_m, training_load),
    )


def _insert_sleep(conn: sqlite3.Connection, day_offset: int, hours: float) -> None:
    d = MONDAY + timedelta(days=day_offset)
    conn.execute(
        "INSERT INTO sleep (date, total_sleep_s, raw_json) VALUES (?, ?, '{}')",
        (d.isoformat(), int(hours * 3600)),
    )


def test_hit_every_target(db_conn: sqlite3.Connection) -> None:
    initialize(db_conn)
    # 3 runs totalling 25km, longest 10km
    _insert_activity(
        db_conn,
        activity_id=1,
        day_offset=0,
        sport="running",
        distance_m=10_000,
        training_load=120,
    )
    _insert_activity(
        db_conn,
        activity_id=2,
        day_offset=2,
        sport="running",
        distance_m=8_000,
        training_load=110,
    )
    _insert_activity(
        db_conn,
        activity_id=3,
        day_offset=4,
        sport="running",
        distance_m=7_000,
        training_load=120,
    )
    _insert_activity(db_conn, activity_id=4, day_offset=5, sport="strength_training")
    for i in range(7):
        _insert_sleep(db_conn, i, 7.5)

    result = score_week(db_conn, _full_plan(), iso_year=ISO_YEAR, iso_week=ISO_WEEK)
    assert result.overall_score == pytest.approx(100.0)
    assert result.misses == []


def test_miss_run_count_shows_in_misses(db_conn: sqlite3.Connection) -> None:
    initialize(db_conn)
    _insert_activity(
        db_conn,
        activity_id=1,
        day_offset=0,
        sport="running",
        distance_m=25_000,
        training_load=350,
    )
    for i in range(7):
        _insert_sleep(db_conn, i, 7.5)

    result = score_week(db_conn, _full_plan(), iso_year=ISO_YEAR, iso_week=ISO_WEEK)
    run_target = next(t for t in result.target_scores if t.target == "runs")
    assert run_target.actual == 1
    assert run_target.score < 100
    assert any("runs" in m for m in result.misses)


def test_no_data_with_only_none_targets_scores_100(
    db_conn: sqlite3.Connection,
) -> None:
    initialize(db_conn)
    plan = Plan.model_validate({"athlete": {"name": "X", "resting_hr": 55, "max_hr": 185}})
    result = score_week(db_conn, plan, iso_year=ISO_YEAR, iso_week=ISO_WEEK)
    assert result.overall_score == 100.0
    assert result.target_scores == []
    assert result.misses == []


def test_long_run_over_120_pct_drops_below_100(
    db_conn: sqlite3.Connection,
) -> None:
    initialize(db_conn)
    # 25km long run vs target 10km → ratio 2.5
    _insert_activity(
        db_conn,
        activity_id=1,
        day_offset=0,
        sport="running",
        distance_m=25_000,
        training_load=200,
    )
    for i in range(7):
        _insert_sleep(db_conn, i, 7.5)
    result = score_week(db_conn, _full_plan(), iso_year=ISO_YEAR, iso_week=ISO_WEEK)
    long_run = next(t for t in result.target_scores if t.target == "long_run_km")
    assert long_run.score < 100


def test_sleep_over_target_does_not_penalise(
    db_conn: sqlite3.Connection,
) -> None:
    initialize(db_conn)
    for i in range(7):
        _insert_sleep(db_conn, i, 10.0)  # way over 7.5
    result = score_week(db_conn, _full_plan(), iso_year=ISO_YEAR, iso_week=ISO_WEEK)
    sleep = next(t for t in result.target_scores if t.target == "sleep_hours_avg")
    assert sleep.score == 100.0
