"""Tests for ingest_range runner (ingest-04)."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

import pytest

from health.db.conn import initialize
from health.ingest.garmin import DayBundle, GarminClient
from health.ingest.runner import IngestSummary, ingest_range


@pytest.fixture
def db(db_conn: sqlite3.Connection) -> sqlite3.Connection:
    initialize(db_conn)
    return db_conn


def _summary_payload(d: date, steps: int = 8000) -> dict[str, Any]:
    return {
        "calendarDate": d.isoformat(),
        "totalSteps": steps,
        "restingHeartRate": 52,
        "bodyBatteryLowestValue": 20,
        "bodyBatteryHighestValue": 90,
        "averageStressLevel": 30,
        "activeKilocalories": 500,
    }


def _sleep_payload(d: date) -> dict[str, Any]:
    return {
        "dailySleepDTO": {
            "calendarDate": d.isoformat(),
            "sleepTimeSeconds": 28800,
            "deepSleepSeconds": 5400,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 7200,
            "awakeSleepSeconds": 1800,
            "sleepScores": {"overall": {"value": 80.0}},
        }
    }


def _hrv_payload(d: date) -> dict[str, Any]:
    return {
        "hrvSummary": {
            "calendarDate": d.isoformat(),
            "weeklyAvg": 55,
            "lastNightAvg": 58,
            "status": "balanced",
        }
    }


def _bc_payload(d: date) -> dict[str, Any]:
    return {
        "calendarDate": d.isoformat(),
        "weight": 70000,
        "bodyFat": 18.0,
        "muscleMass": 55000,
    }


def _activity_payload(activity_id: int, d: date) -> dict[str, Any]:
    return {
        "activityId": activity_id,
        "startTimeGMT": f"{d.isoformat()} 07:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 3600.0,
        "distance": 10000.0,
        "averageHR": 150.0,
        "activityTrainingLoad": 120.0,
        "aerobicTrainingEffect": 3.5,
        "anaerobicTrainingEffect": 1.0,
    }


class StubClient:
    """Stub GarminClient: returns canned bundles, optionally raises per date."""

    def __init__(
        self,
        bundles: dict[date, DayBundle],
        activities: list[dict[str, Any]],
        fail_dates: set[date] | None = None,
        activities_exc: Exception | None = None,
    ) -> None:
        self.bundles = bundles
        self.activities = activities
        self.fail_dates = fail_dates or set()
        self.activities_exc = activities_exc
        self.day_calls = 0
        self.activity_calls = 0

    def fetch_day(self, d: date) -> DayBundle:
        self.day_calls += 1
        if d in self.fail_dates:
            raise RuntimeError(f"boom on {d}")
        return self.bundles[d]

    def fetch_activities(self, start: date, end: date) -> list[dict[str, Any]]:
        self.activity_calls += 1
        if self.activities_exc is not None:
            raise self.activities_exc
        return self.activities


def _full_bundle(d: date) -> DayBundle:
    return DayBundle(
        date=d,
        summary=_summary_payload(d),
        sleep=_sleep_payload(d),
        hrv=_hrv_payload(d),
        body_composition=_bc_payload(d),
    )


def test_happy_path_three_days(db: sqlite3.Connection) -> None:
    start = date(2026, 5, 1)
    end = date(2026, 5, 3)
    dates = [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)]
    bundles = {d: _full_bundle(d) for d in dates}
    activities = [_activity_payload(i + 1, dates[i]) for i in range(3)]
    client = StubClient(bundles, activities)

    summary = ingest_range(db, client, start, end)  # type: ignore[arg-type]
    # reason: StubClient duck-types GarminClient for tests.

    assert isinstance(summary, IngestSummary)
    assert summary.errors == []
    assert summary.days_requested == 3
    # 3 days * 4 bundle fields + 3 activities = 15
    assert summary.rows_written == 15
    assert summary.run_id > 0
    assert summary.finished_at >= summary.started_at

    assert db.execute("SELECT COUNT(*) AS n FROM daily_summary").fetchone()["n"] == 3
    assert db.execute("SELECT COUNT(*) AS n FROM sleep").fetchone()["n"] == 3
    assert db.execute("SELECT COUNT(*) AS n FROM hrv").fetchone()["n"] == 3
    assert db.execute("SELECT COUNT(*) AS n FROM body_composition").fetchone()["n"] == 3
    assert db.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"] == 3

    row = db.execute("SELECT * FROM ingest_runs WHERE id = ?", (summary.run_id,)).fetchone()
    assert row["error"] is None
    assert row["days_requested"] == 3
    assert row["rows_written"] == 15


def test_one_bad_day_does_not_abort(db: sqlite3.Connection) -> None:
    start = date(2026, 5, 1)
    end = date(2026, 5, 3)
    dates = [date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3)]
    bundles = {d: _full_bundle(d) for d in dates}
    client = StubClient(bundles, activities=[], fail_dates={date(2026, 5, 2)})

    summary = ingest_range(db, client, start, end)  # type: ignore[arg-type]
    # reason: StubClient duck-types GarminClient for tests.

    assert len(summary.errors) == 1
    assert summary.errors[0].startswith("2026-05-02:")
    # 2 good days * 4 fields = 8 rows
    assert summary.rows_written == 8
    assert db.execute("SELECT COUNT(*) AS n FROM daily_summary").fetchone()["n"] == 2

    row = db.execute("SELECT * FROM ingest_runs WHERE id = ?", (summary.run_id,)).fetchone()
    assert row["error"] is not None
    assert "2026-05-02" in row["error"]


def test_idempotent_double_run(db: sqlite3.Connection) -> None:
    start = date(2026, 5, 1)
    end = date(2026, 5, 2)
    dates = [date(2026, 5, 1), date(2026, 5, 2)]
    bundles = {d: _full_bundle(d) for d in dates}
    activities = [_activity_payload(1, dates[0]), _activity_payload(2, dates[1])]
    client = StubClient(bundles, activities)

    s1 = ingest_range(db, client, start, end)  # type: ignore[arg-type]
    s2 = ingest_range(db, client, start, end)  # type: ignore[arg-type]
    # reason: StubClient duck-types GarminClient for tests.

    assert s1.rows_written == s2.rows_written
    assert db.execute("SELECT COUNT(*) AS n FROM daily_summary").fetchone()["n"] == 2
    assert db.execute("SELECT COUNT(*) AS n FROM sleep").fetchone()["n"] == 2
    assert db.execute("SELECT COUNT(*) AS n FROM hrv").fetchone()["n"] == 2
    assert db.execute("SELECT COUNT(*) AS n FROM body_composition").fetchone()["n"] == 2
    assert db.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"] == 2
    assert db.execute("SELECT COUNT(*) AS n FROM ingest_runs").fetchone()["n"] == 2


def test_empty_range_single_day(db: sqlite3.Connection) -> None:
    d = date(2026, 5, 1)
    bundles = {d: _full_bundle(d)}
    client = StubClient(bundles, activities=[])

    summary = ingest_range(db, client, d, d)  # type: ignore[arg-type]
    # reason: StubClient duck-types GarminClient for tests.

    assert summary.days_requested == 1
    assert client.day_calls == 1
    assert client.activity_calls == 1
    assert summary.rows_written == 4
    assert summary.errors == []


def test_activities_failure_continues(db: sqlite3.Connection) -> None:
    d = date(2026, 5, 1)
    bundles = {d: _full_bundle(d)}
    client = StubClient(bundles, activities=[], activities_exc=RuntimeError("activities boom"))

    summary = ingest_range(db, client, d, d)  # type: ignore[arg-type]
    # reason: StubClient duck-types GarminClient for tests.

    assert any(e.startswith("activities:") for e in summary.errors)
    # day succeeded => 4 rows
    assert summary.rows_written == 4


def test_ingest_range_typed_signature() -> None:
    # Ensure module exposes the expected callable.
    from health.ingest import runner

    assert callable(runner.ingest_range)
    assert hasattr(runner, "IngestSummary")


def test_uses_real_garmin_client_type() -> None:
    # Ensure the import is wired (no real network call).
    assert GarminClient is not None
