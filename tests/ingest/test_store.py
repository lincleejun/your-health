"""Tests for idempotent upsert helpers (ingest-03)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime

import pytest

from health.db.conn import initialize
from health.ingest.models import (
    Activity,
    BodyComposition,
    DailySummary,
    HrvDay,
    Sleep,
)
from health.ingest.store import (
    record_ingest_run,
    upsert_activity,
    upsert_body_composition,
    upsert_daily_summary,
    upsert_hrv,
    upsert_sleep,
)


@pytest.fixture
def db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    initialize(db_conn)
    return db_conn


def _activity(activity_id: int = 1, sport: str = "running", avg_hr: float = 150.0) -> Activity:
    return Activity(
        activity_id=activity_id,
        start_ts=datetime(2026, 5, 1, 7, 0, tzinfo=UTC),
        sport=sport,
        duration_s=3600.0,
        distance_m=10000.0,
        avg_hr=avg_hr,
        training_load=120.0,
        aerobic_te=3.5,
        anaerobic_te=1.0,
        raw_json={"activityId": activity_id, "sport": sport},
    )


def _daily(d: date = date(2026, 5, 1), steps: int = 8000) -> DailySummary:
    return DailySummary(
        date=d,
        steps=steps,
        resting_hr=52.0,
        body_battery_min=20,
        body_battery_max=90,
        stress_avg=30.0,
        calories_active=500.0,
        raw_json={"calendarDate": d.isoformat(), "totalSteps": steps},
    )


def _sleep(d: date = date(2026, 5, 1), score: float = 80.0) -> Sleep:
    return Sleep(
        date=d,
        total_sleep_s=28800,
        deep_s=5400,
        light_s=14400,
        rem_s=7200,
        awake_s=1800,
        sleep_score=score,
        raw_json={"dailySleepDTO": {"calendarDate": d.isoformat()}},
    )


def _hrv(d: date = date(2026, 5, 1), weekly_avg: float = 55.0) -> HrvDay:
    return HrvDay(
        date=d,
        weekly_avg=weekly_avg,
        last_night_avg=58.0,
        status="balanced",
        raw_json={"hrvSummary": {"calendarDate": d.isoformat()}},
    )


def _bc(d: date = date(2026, 5, 1), weight_kg: float = 70.0) -> BodyComposition:
    return BodyComposition(
        date=d,
        weight_kg=weight_kg,
        body_fat_pct=18.0,
        muscle_mass_kg=55.0,
        raw_json={"calendarDate": d.isoformat(), "weight": weight_kg * 1000},
    )


def test_upsert_activity_round_trip(db: sqlite3.Connection) -> None:
    upsert_activity(db, _activity())
    row = db.execute("SELECT * FROM activities WHERE activity_id = 1").fetchone()
    assert row["sport"] == "running"
    assert row["avg_hr"] == 150.0
    assert json.loads(row["raw_json"]) == {"activityId": 1, "sport": "running"}


def test_upsert_activity_idempotent_updates(db: sqlite3.Connection) -> None:
    upsert_activity(db, _activity(avg_hr=150.0))
    upsert_activity(db, _activity(avg_hr=160.0))
    rows = db.execute("SELECT avg_hr FROM activities WHERE activity_id = 1").fetchall()
    assert len(rows) == 1
    assert rows[0]["avg_hr"] == 160.0


def test_upsert_daily_summary_round_trip_and_idempotent(db: sqlite3.Connection) -> None:
    upsert_daily_summary(db, _daily(steps=8000))
    upsert_daily_summary(db, _daily(steps=9500))
    rows = db.execute("SELECT * FROM daily_summary").fetchall()
    assert len(rows) == 1
    assert rows[0]["steps"] == 9500
    assert rows[0]["date"] == "2026-05-01"


def test_upsert_sleep_round_trip_and_idempotent(db: sqlite3.Connection) -> None:
    upsert_sleep(db, _sleep(score=80.0))
    upsert_sleep(db, _sleep(score=85.0))
    rows = db.execute("SELECT * FROM sleep").fetchall()
    assert len(rows) == 1
    assert rows[0]["sleep_score"] == 85.0


def test_upsert_hrv_round_trip_and_idempotent(db: sqlite3.Connection) -> None:
    upsert_hrv(db, _hrv(weekly_avg=55.0))
    upsert_hrv(db, _hrv(weekly_avg=60.0))
    rows = db.execute("SELECT * FROM hrv").fetchall()
    assert len(rows) == 1
    assert rows[0]["weekly_avg"] == 60.0
    assert rows[0]["status"] == "balanced"


def test_upsert_body_composition_round_trip_and_idempotent(db: sqlite3.Connection) -> None:
    upsert_body_composition(db, _bc(weight_kg=70.0))
    upsert_body_composition(db, _bc(weight_kg=71.5))
    rows = db.execute("SELECT * FROM body_composition").fetchall()
    assert len(rows) == 1
    assert rows[0]["weight_kg"] == 71.5


def test_record_ingest_run_returns_positive_id(db: sqlite3.Connection) -> None:
    run_id = record_ingest_run(db, days_requested=7, rows_written=42)
    assert isinstance(run_id, int)
    assert run_id > 0
    row = db.execute("SELECT * FROM ingest_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["days_requested"] == 7
    assert row["rows_written"] == 42
    assert row["error"] is None
    assert row["started_at"] is not None


def test_record_ingest_run_with_error(db: sqlite3.Connection) -> None:
    run_id = record_ingest_run(db, days_requested=3, rows_written=0, error="auth failed")
    row = db.execute("SELECT error FROM ingest_runs WHERE id = ?", (run_id,)).fetchone()
    assert row["error"] == "auth failed"


def test_raw_json_round_trip(db: sqlite3.Connection) -> None:
    payload = {"calendarDate": "2026-05-01", "nested": {"a": 1, "b": [1, 2, 3]}}
    summary = DailySummary(date=date(2026, 5, 1), steps=100, raw_json=payload)
    upsert_daily_summary(db, summary)
    row = db.execute("SELECT raw_json FROM daily_summary").fetchone()
    assert json.loads(row["raw_json"]) == payload


def test_upserts_do_not_commit(db: sqlite3.Connection) -> None:
    upsert_activity(db, _activity())
    db.rollback()
    rows = db.execute("SELECT COUNT(*) AS n FROM activities").fetchone()
    assert rows["n"] == 0
