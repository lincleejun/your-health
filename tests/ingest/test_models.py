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

D = date(2026, 5, 10)


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
    d = DailySummary.from_garmin(payload, for_date=D)
    assert d is not None
    assert d.date == D
    assert d.steps == 8421
    assert d.resting_hr == 48.0
    assert d.body_battery_min == 20
    assert d.body_battery_max == 95
    assert d.stress_avg == 31.0
    assert d.calories_active == 612.0


def test_daily_summary_falls_back_to_for_date_when_calendar_date_missing() -> None:
    d = DailySummary.from_garmin({"totalSteps": 5000}, for_date=D)
    assert d is not None
    assert d.date == D
    assert d.steps == 5000


def test_daily_summary_returns_none_on_empty_payload() -> None:
    assert DailySummary.from_garmin({}, for_date=D) is None


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
    s = Sleep.from_garmin(payload, for_date=D)
    assert s is not None
    assert s.date == D
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
    s = Sleep.from_garmin(payload, for_date=D)
    assert s is not None
    assert s.sleep_score is None
    assert s.deep_s is None


def test_sleep_returns_none_when_dto_missing() -> None:
    assert Sleep.from_garmin({}, for_date=D) is None
    assert Sleep.from_garmin({"sleepMovement": []}, for_date=D) is None


def test_hrv_from_garmin_happy_path() -> None:
    payload = {
        "hrvSummary": {
            "calendarDate": "2026-05-10",
            "weeklyAvg": 55.0,
            "lastNightAvg": 60.0,
            "status": "BALANCED",
        }
    }
    h = HrvDay.from_garmin(payload, for_date=D)
    assert h is not None
    assert h.date == D
    assert h.weekly_avg == 55.0
    assert h.last_night_avg == 60.0
    assert h.status == "BALANCED"


def test_hrv_returns_none_on_empty_payload() -> None:
    assert HrvDay.from_garmin({}, for_date=D) is None
    assert HrvDay.from_garmin({"hrvSummary": {}}, for_date=D) is None


def test_body_composition_from_dateWeightList() -> None:
    """Real Garmin shape: a list of weighings under ``dateWeightList``."""
    payload = {
        "startDate": "2026-05-10",
        "endDate": "2026-05-10",
        "dateWeightList": [
            {
                "date": "2026-05-10",
                "weight": 72500.0,
                "bodyFat": 18.5,
                "muscleMass": 33000.0,
            }
        ],
        "totalAverage": {},
    }
    b = BodyComposition.from_garmin(payload, for_date=D)
    assert b is not None
    assert b.date == D
    assert b.weight_kg == 72.5
    assert b.body_fat_pct == 18.5
    assert b.muscle_mass_kg == 33.0


def test_body_composition_returns_none_when_no_weighings() -> None:
    payload = {
        "startDate": "2026-05-10",
        "endDate": "2026-05-10",
        "dateWeightList": [],
        "totalAverage": {},
    }
    assert BodyComposition.from_garmin(payload, for_date=D) is None


def test_body_composition_accepts_legacy_flat_payload() -> None:
    """Older shape (or tests) might pass a flat dict directly."""
    payload = {"calendarDate": "2026-05-10", "weight": 72500.0, "bodyFat": 18.5}
    b = BodyComposition.from_garmin(payload, for_date=D)
    assert b is not None
    assert b.weight_kg == 72.5
    assert b.body_fat_pct == 18.5
