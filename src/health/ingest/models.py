"""Pydantic models for Garmin Connect payloads.

Each model exposes a :py:meth:`from_garmin` classmethod that tolerates missing
optional fields — the upstream API frequently omits keys when a device did not
record a given metric. The raw payload is preserved on ``raw_json`` so we can
re-derive new columns without re-pulling.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict


def _parse_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _parse_datetime_utc(value: Any) -> datetime:
    """Parse a Garmin timestamp into a tz-aware UTC datetime.

    Garmin returns ``startTimeGMT`` as ``"YYYY-MM-DD HH:MM:SS"`` (naive but GMT).
    We normalise to a tz-aware UTC datetime so downstream code never sees naive
    datetimes.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).replace("T", " ").rstrip("Z").strip()
    dt = datetime.fromisoformat(text)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True)


class Activity(_Base):
    activity_id: int
    start_ts: datetime
    sport: str
    duration_s: float | None = None
    distance_m: float | None = None
    avg_hr: float | None = None
    training_load: float | None = None
    aerobic_te: float | None = None
    anaerobic_te: float | None = None
    raw_json: dict[str, Any]

    @classmethod
    def from_garmin(cls, payload: dict[str, Any]) -> Self:
        activity_type = payload.get("activityType") or {}
        sport = activity_type.get("typeKey") or "unknown"
        return cls(
            activity_id=int(payload["activityId"]),
            start_ts=_parse_datetime_utc(payload["startTimeGMT"]),
            sport=sport,
            duration_s=payload.get("duration"),
            distance_m=payload.get("distance"),
            avg_hr=payload.get("averageHR"),
            training_load=payload.get("activityTrainingLoad"),
            aerobic_te=payload.get("aerobicTrainingEffect"),
            anaerobic_te=payload.get("anaerobicTrainingEffect"),
            raw_json=payload,
        )


class DailySummary(_Base):
    date: date
    steps: int | None = None
    resting_hr: float | None = None
    body_battery_min: int | None = None
    body_battery_max: int | None = None
    stress_avg: float | None = None
    calories_active: float | None = None
    raw_json: dict[str, Any]

    @classmethod
    def from_garmin(cls, payload: dict[str, Any]) -> Self:
        return cls(
            date=_parse_date(payload["calendarDate"]),
            steps=payload.get("totalSteps"),
            resting_hr=payload.get("restingHeartRate"),
            body_battery_min=payload.get("bodyBatteryLowestValue"),
            body_battery_max=payload.get("bodyBatteryHighestValue"),
            stress_avg=payload.get("averageStressLevel"),
            calories_active=payload.get("activeKilocalories"),
            raw_json=payload,
        )


class Sleep(_Base):
    date: date
    total_sleep_s: int | None = None
    deep_s: int | None = None
    light_s: int | None = None
    rem_s: int | None = None
    awake_s: int | None = None
    sleep_score: float | None = None
    raw_json: dict[str, Any]

    @classmethod
    def from_garmin(cls, payload: dict[str, Any]) -> Self:
        dto = payload.get("dailySleepDTO") or {}
        scores = dto.get("sleepScores") or {}
        overall = scores.get("overall") or {}
        return cls(
            date=_parse_date(dto["calendarDate"]),
            total_sleep_s=dto.get("sleepTimeSeconds"),
            deep_s=dto.get("deepSleepSeconds"),
            light_s=dto.get("lightSleepSeconds"),
            rem_s=dto.get("remSleepSeconds"),
            awake_s=dto.get("awakeSleepSeconds"),
            sleep_score=overall.get("value"),
            raw_json=payload,
        )


class HrvDay(_Base):
    date: date
    weekly_avg: float | None = None
    last_night_avg: float | None = None
    status: str | None = None
    raw_json: dict[str, Any]

    @classmethod
    def from_garmin(cls, payload: dict[str, Any]) -> Self:
        summary = payload.get("hrvSummary") or {}
        return cls(
            date=_parse_date(summary["calendarDate"]),
            weekly_avg=summary.get("weeklyAvg"),
            last_night_avg=summary.get("lastNightAvg"),
            status=summary.get("status"),
            raw_json=payload,
        )


class BodyComposition(_Base):
    date: date
    weight_kg: float | None = None
    body_fat_pct: float | None = None
    muscle_mass_kg: float | None = None
    raw_json: dict[str, Any]

    @classmethod
    def from_garmin(cls, payload: dict[str, Any]) -> Self:
        weight = payload.get("weight")
        muscle = payload.get("muscleMass")
        return cls(
            date=_parse_date(payload["calendarDate"]),
            weight_kg=weight / 1000.0 if weight is not None else None,
            body_fat_pct=payload.get("bodyFat"),
            muscle_mass_kg=muscle / 1000.0 if muscle is not None else None,
            raw_json=payload,
        )
