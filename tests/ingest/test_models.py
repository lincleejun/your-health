"""Tests for Pydantic models that parse Garmin Connect payloads."""

from __future__ import annotations

from datetime import UTC, date, datetime

from health.ingest.models import (
    Activity,
    BodyComposition,
    DailySummary,
    HrvDay,
    Sleep,
)


def test_activity_from_garmin_happy_path() -> None:
    payload = {
        "activityId": 12345,
        "startTimeGMT": "2026-05-10 06:30:00",
        "activityType": {"typeKey": "running"},
        "duration": 3600.5,
        "distance": 10000.0,
        "averageHR": 152.0,
        "activityTrainingLoad": 120.0,
        "aerobicTrainingEffect": 3.4,
        "anaerobicTrainingEffect": 1.1,
    }
    a = Activity.from_garmin(payload)
    assert a.activity_id == 12345
    assert a.sport == "running"
    assert a.start_ts == datetime(2026, 5, 10, 6, 30, tzinfo=UTC)
    assert a.duration_s == 3600.5
    assert a.distance_m == 10000.0
    assert a.avg_hr == 152.0
    assert a.training_load == 120.0
    assert a.aerobic_te == 3.4
    assert a.anaerobic_te == 1.1
    assert a.raw_json == payload


def test_activity_from_garmin_tolerates_missing_fields() -> None:
    payload = {
        "activityId": 999,
        "startTimeGMT": "2026-05-10 06:30:00",
        "activityType": {"typeKey": "cycling"},
    }
    a = Activity.from_garmin(payload)
    assert a.activity_id == 999
    assert a.sport == "cycling"
    assert a.duration_s is None
    assert a.distance_m is None
    assert a.avg_hr is None
    assert a.training_load is None


def test_daily_summary_from_garmin_happy_path() -> None:
    payload = {
        "calendarDate": "2026-05-10",
        "totalSteps": 8421,
        "restingHeartRate": 48.0,
        "bodyBatteryLowestValue": 20,
        "bodyBatteryHighestValue": 95,
        "averageStressLevel": 31.0,
        "activeKilocalories": 612.0,
    }
    d = DailySummary.from_garmin(payload)
    assert d.date == date(2026, 5, 10)
    assert d.steps == 8421
    assert d.resting_hr == 48.0
    assert d.body_battery_min == 20
    assert d.body_battery_max == 95
    assert d.stress_avg == 31.0
    assert d.calories_active == 612.0


def test_daily_summary_tolerates_missing() -> None:
    d = DailySummary.from_garmin({"calendarDate": "2026-05-10"})
    assert d.date == date(2026, 5, 10)
    assert d.steps is None
    assert d.resting_hr is None


def test_sleep_from_garmin_nested_dto() -> None:
    payload = {
        "dailySleepDTO": {
            "calendarDate": "2026-05-10",
            "sleepTimeSeconds": 27000,
            "deepSleepSeconds": 4200,
            "lightSleepSeconds": 14400,
            "remSleepSeconds": 7200,
            "awakeSleepSeconds": 1200,
            "sleepScores": {"overall": {"value": 82.0}},
        }
    }
    s = Sleep.from_garmin(payload)
    assert s.date == date(2026, 5, 10)
    assert s.total_sleep_s == 27000
    assert s.deep_s == 4200
    assert s.light_s == 14400
    assert s.rem_s == 7200
    assert s.awake_s == 1200
    assert s.sleep_score == 82.0


def test_sleep_tolerates_missing_score() -> None:
    payload = {
        "dailySleepDTO": {
            "calendarDate": "2026-05-10",
            "sleepTimeSeconds": 27000,
        }
    }
    s = Sleep.from_garmin(payload)
    assert s.sleep_score is None
    assert s.deep_s is None


def test_hrv_from_garmin_happy_path() -> None:
    payload = {
        "hrvSummary": {
            "calendarDate": "2026-05-10",
            "weeklyAvg": 55.0,
            "lastNightAvg": 60.0,
            "status": "BALANCED",
        }
    }
    h = HrvDay.from_garmin(payload)
    assert h.date == date(2026, 5, 10)
    assert h.weekly_avg == 55.0
    assert h.last_night_avg == 60.0
    assert h.status == "BALANCED"


def test_hrv_tolerates_missing_summary() -> None:
    h = HrvDay.from_garmin({"hrvSummary": {"calendarDate": "2026-05-10"}})
    assert h.date == date(2026, 5, 10)
    assert h.weekly_avg is None
    assert h.status is None


def test_body_composition_from_garmin_happy_path() -> None:
    payload = {
        "calendarDate": "2026-05-10",
        "weight": 72500.0,
        "bodyFat": 18.5,
        "muscleMass": 33000.0,
    }
    b = BodyComposition.from_garmin(payload)
    assert b.date == date(2026, 5, 10)
    assert b.weight_kg == 72.5
    assert b.body_fat_pct == 18.5
    assert b.muscle_mass_kg == 33.0


def test_body_composition_tolerates_missing() -> None:
    b = BodyComposition.from_garmin({"calendarDate": "2026-05-10"})
    assert b.date == date(2026, 5, 10)
    assert b.weight_kg is None
    assert b.body_fat_pct is None
