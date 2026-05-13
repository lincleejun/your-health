"""Idempotent UPSERT helpers for the health database.

Each function takes an open :class:`sqlite3.Connection` and a validated Pydantic
model, and writes the row using ``INSERT ... ON CONFLICT(<pk>) DO UPDATE``.
The caller owns the transaction — these helpers never commit or rollback.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from health.ingest.models import (
    Activity,
    BodyComposition,
    DailySummary,
    HrvDay,
    Sleep,
)


def _dumps(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, default=str)


_ACTIVITY_SQL = """
INSERT INTO activities (
    activity_id, start_ts, sport, duration_s, distance_m,
    avg_hr, training_load, aerobic_te, anaerobic_te, raw_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(activity_id) DO UPDATE SET
    start_ts      = excluded.start_ts,
    sport         = excluded.sport,
    duration_s    = excluded.duration_s,
    distance_m    = excluded.distance_m,
    avg_hr        = excluded.avg_hr,
    training_load = excluded.training_load,
    aerobic_te    = excluded.aerobic_te,
    anaerobic_te  = excluded.anaerobic_te,
    raw_json      = excluded.raw_json
"""


def upsert_activity(conn: sqlite3.Connection, activity: Activity) -> None:
    conn.execute(
        _ACTIVITY_SQL,
        (
            activity.activity_id,
            activity.start_ts.isoformat(),
            activity.sport,
            activity.duration_s,
            activity.distance_m,
            activity.avg_hr,
            activity.training_load,
            activity.aerobic_te,
            activity.anaerobic_te,
            _dumps(activity.raw_json),
        ),
    )


_DAILY_SQL = """
INSERT INTO daily_summary (
    date, steps, resting_hr, body_battery_min, body_battery_max,
    stress_avg, calories_active, raw_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(date) DO UPDATE SET
    steps            = excluded.steps,
    resting_hr       = excluded.resting_hr,
    body_battery_min = excluded.body_battery_min,
    body_battery_max = excluded.body_battery_max,
    stress_avg       = excluded.stress_avg,
    calories_active  = excluded.calories_active,
    raw_json         = excluded.raw_json
"""


def upsert_daily_summary(conn: sqlite3.Connection, summary: DailySummary) -> None:
    conn.execute(
        _DAILY_SQL,
        (
            summary.date.isoformat(),
            summary.steps,
            summary.resting_hr,
            summary.body_battery_min,
            summary.body_battery_max,
            summary.stress_avg,
            summary.calories_active,
            _dumps(summary.raw_json),
        ),
    )


_SLEEP_SQL = """
INSERT INTO sleep (
    date, total_sleep_s, deep_s, light_s, rem_s, awake_s, sleep_score, raw_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(date) DO UPDATE SET
    total_sleep_s = excluded.total_sleep_s,
    deep_s        = excluded.deep_s,
    light_s       = excluded.light_s,
    rem_s         = excluded.rem_s,
    awake_s       = excluded.awake_s,
    sleep_score   = excluded.sleep_score,
    raw_json      = excluded.raw_json
"""


def upsert_sleep(conn: sqlite3.Connection, sleep: Sleep) -> None:
    conn.execute(
        _SLEEP_SQL,
        (
            sleep.date.isoformat(),
            sleep.total_sleep_s,
            sleep.deep_s,
            sleep.light_s,
            sleep.rem_s,
            sleep.awake_s,
            sleep.sleep_score,
            _dumps(sleep.raw_json),
        ),
    )


_HRV_SQL = """
INSERT INTO hrv (date, weekly_avg, last_night_avg, status, raw_json)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(date) DO UPDATE SET
    weekly_avg     = excluded.weekly_avg,
    last_night_avg = excluded.last_night_avg,
    status         = excluded.status,
    raw_json       = excluded.raw_json
"""


def upsert_hrv(conn: sqlite3.Connection, hrv: HrvDay) -> None:
    conn.execute(
        _HRV_SQL,
        (
            hrv.date.isoformat(),
            hrv.weekly_avg,
            hrv.last_night_avg,
            hrv.status,
            _dumps(hrv.raw_json),
        ),
    )


_BC_SQL = """
INSERT INTO body_composition (date, weight_kg, body_fat_pct, muscle_mass_kg, raw_json)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(date) DO UPDATE SET
    weight_kg      = excluded.weight_kg,
    body_fat_pct   = excluded.body_fat_pct,
    muscle_mass_kg = excluded.muscle_mass_kg,
    raw_json       = excluded.raw_json
"""


def upsert_body_composition(conn: sqlite3.Connection, bc: BodyComposition) -> None:
    conn.execute(
        _BC_SQL,
        (
            bc.date.isoformat(),
            bc.weight_kg,
            bc.body_fat_pct,
            bc.muscle_mass_kg,
            _dumps(bc.raw_json),
        ),
    )


def record_ingest_run(
    conn: sqlite3.Connection,
    days_requested: int,
    rows_written: int,
    error: str | None = None,
) -> int:
    """Insert an ingest_runs row and return its autoincrement id."""
    now = datetime.now(UTC).isoformat()
    cur = conn.execute(
        "INSERT INTO ingest_runs (started_at, finished_at, days_requested, rows_written, error) "
        "VALUES (?, ?, ?, ?, ?)",
        (now, now, days_requested, rows_written, error),
    )
    run_id = cur.lastrowid
    if run_id is None:  # pragma: no cover - SQLite always populates lastrowid for INSERT
        raise RuntimeError("INSERT into ingest_runs did not return a lastrowid")
    return run_id
