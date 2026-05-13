"""Pydantic models for Garmin Connect payloads.

Each day-scoped model exposes ``from_garmin(payload, *, for_date) -> Self | None``.
The classmethod is tolerant of three real-world quirks of the Garmin API:

* Some endpoints return an empty dict when no data was recorded that day — we
  return ``None`` so the caller can simply skip the insert.
* Some endpoints omit ``calendarDate`` at the level we expect — we fall back to
  the ``for_date`` the caller is asking about.
* Some payloads bury the day's record inside a list (``dateWeightList``) or a
  nested DTO (``dailySleepDTO``) — we unwrap.

The original payload is preserved on ``raw_json`` so we can re-derive new
columns later without re-pulling from Garmin.
"""

from __future__ import annotations

from datetime import UTC, datetime
from datetime import date as _date  # avoid name clash with model field ``date``
from typing import Any, Self

from pydantic import BaseModel, ConfigDict


def _parse_date(value: Any) -> _date:
    if isinstance(value, _date) and not isinstance(value, datetime):
        return value
    return _date.fromisoformat(str(value))


def _coerce_date(value: Any, *, fallback: _date) -> _date:
    """Best-effort date parser. Accepts ISO strings, unix-ms ints, falls back."""
    if value is None or value == "":
        return fallback
    if isinstance(value, _date) and not isinstance(value, datetime):
        return value
    if isinstance(value, int | float):
        # Garmin sometimes encodes dates as unix milliseconds.
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC).date()
    try:
        return _date.fromisoformat(str(value))
    except ValueError:
        return fallback


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
    date: _date
    steps: int | None = None
    resting_hr: float | None = None
    body_battery_min: int | None = None
    body_battery_max: int | None = None
    stress_avg: float | None = None
    calories_active: float | None = None
    raw_json: dict[str, Any]

    @classmethod
    def from_garmin(cls, payload: dict[str, Any], *, for_date: _date) -> Self | None:
        if not payload:
            return None
        return cls(
            date=_coerce_date(payload.get("calendarDate"), fallback=for_date),
            steps=payload.get("totalSteps"),
            resting_hr=payload.get("restingHeartRate"),
            body_battery_min=payload.get("bodyBatteryLowestValue"),
            body_battery_max=payload.get("bodyBatteryHighestValue"),
            stress_avg=payload.get("averageStressLevel"),
            calories_active=payload.get("activeKilocalories"),
            raw_json=payload,
        )


class Sleep(_Base):
    date: _date
    total_sleep_s: int | None = None
    deep_s: int | None = None
    light_s: int | None = None
    rem_s: int | None = None
    awake_s: int | None = None
    sleep_score: float | None = None
    raw_json: dict[str, Any]

    @classmethod
    def from_garmin(cls, payload: dict[str, Any], *, for_date: _date) -> Self | None:
        dto = payload.get("dailySleepDTO") or {}
        if not dto:
            return None
        scores = dto.get("sleepScores") or {}
        overall = scores.get("overall") or {}
        return cls(
            date=_coerce_date(dto.get("calendarDate"), fallback=for_date),
            total_sleep_s=dto.get("sleepTimeSeconds"),
            deep_s=dto.get("deepSleepSeconds"),
            light_s=dto.get("lightSleepSeconds"),
            rem_s=dto.get("remSleepSeconds"),
            awake_s=dto.get("awakeSleepSeconds"),
            sleep_score=overall.get("value"),
            raw_json=payload,
        )


class HrvDay(_Base):
    date: _date
    weekly_avg: float | None = None
    last_night_avg: float | None = None
    status: str | None = None
    raw_json: dict[str, Any]

    @classmethod
    def from_garmin(cls, payload: dict[str, Any], *, for_date: _date) -> Self | None:
        summary = payload.get("hrvSummary") or {}
        if not summary:
            return None
        return cls(
            date=_coerce_date(summary.get("calendarDate"), fallback=for_date),
            weekly_avg=summary.get("weeklyAvg"),
            last_night_avg=summary.get("lastNightAvg"),
            status=summary.get("status"),
            raw_json=payload,
        )


class BodyComposition(_Base):
    date: _date
    weight_kg: float | None = None
    body_fat_pct: float | None = None
    muscle_mass_kg: float | None = None
    raw_json: dict[str, Any]

    @classmethod
    def from_garmin(cls, payload: dict[str, Any], *, for_date: _date) -> Self | None:
        # Real Garmin shape is ``{dateWeightList: [...], totalAverage: {...}, ...}``.
        # We persist the first weighing for the day; if there were none, skip.
        items = payload.get("dateWeightList") or []
        record: dict[str, Any]
        if items:
            record = items[0]
        elif "calendarDate" in payload or "weight" in payload:
            # Older / flattened shape — treat the payload itself as the record.
            record = payload
        else:
            return None
        weight = record.get("weight")
        muscle = record.get("muscleMass")
        return cls(
            date=_coerce_date(record.get("calendarDate") or record.get("date"), fallback=for_date),
            weight_kg=weight / 1000.0 if weight is not None else None,
            body_fat_pct=record.get("bodyFat"),
            muscle_mass_kg=muscle / 1000.0 if muscle is not None else None,
            raw_json=payload,
        )
