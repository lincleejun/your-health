"""Weekly adherence scoring against ``plan.weekly_targets``.

Compares the actual training / sleep load in one ISO week to the user's
weekly targets and emits a per-target score (0..100) plus an overall
weighted score and a list of human-readable misses (score < 80).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from health.plan.schema import Plan, WeeklyTargets

RUN_SPORTS = ("running", "treadmill_running", "indoor_running")
STRENGTH_SPORTS = (
    "strength_training",
    "indoor_cardio",
    "weights",
    "fitness_equipment",
)

# Weighted-mean weights for the overall score.
WEIGHTS: dict[str, float] = {
    "runs": 1.0,
    "run_distance_km": 1.0,
    "long_run_km": 1.0,
    "strength_sessions": 0.5,
    "sleep_hours_avg": 0.5,
    "weekly_load_target": 1.0,
}

COUNT_TARGETS = {"runs", "strength_sessions"}
AT_LEAST_TARGETS = {
    "run_distance_km",
    "long_run_km",
    "weekly_load_target",
    "sleep_hours_avg",
}
MISS_THRESHOLD = 80.0


@dataclass(frozen=True)
class TargetScore:
    target: str
    planned: float
    actual: float
    score: float
    delta: float


@dataclass(frozen=True)
class WeeklyAdherence:
    iso_year: int
    iso_week: int
    overall_score: float
    target_scores: list[TargetScore]
    misses: list[str]


def _iso_week_bounds(iso_year: int, iso_week: int) -> tuple[date, date]:
    """Return (monday, sunday_inclusive) for an ISO year/week."""
    monday = date.fromisocalendar(iso_year, iso_week, 1)
    return monday, monday + timedelta(days=6)


def _score_count(planned: float, actual: float) -> float:
    if planned <= 0:
        return 100.0
    return min(100.0, 100.0 * actual / planned)


def _score_at_least(planned: float, actual: float, *, penalise_over: bool) -> float:
    if planned <= 0:
        return 100.0
    ratio = actual / planned
    if ratio <= 1:
        return min(100.0, 100.0 * ratio)
    if not penalise_over:
        return 100.0
    # Over by ≥20% starts losing points (50 per unit-of-ratio over 1.2).
    return max(0.0, 100.0 - 50.0 * (ratio - 1.2))


def _collect_actuals(conn: sqlite3.Connection, monday: date, sunday: date) -> dict[str, float]:
    start = monday.isoformat()
    # start_ts is an ISO timestamp; comparing strings against a date prefix works
    # because ISO-8601 sorts lexicographically. Use exclusive upper bound.
    end_exclusive = (sunday + timedelta(days=1)).isoformat()

    run_placeholders = ",".join("?" for _ in RUN_SPORTS)
    strength_placeholders = ",".join("?" for _ in STRENGTH_SPORTS)

    runs_row = conn.execute(
        f"SELECT COUNT(*) AS n, COALESCE(SUM(distance_m), 0) AS dist,"
        f" COALESCE(MAX(distance_m), 0) AS longest"
        f" FROM activities WHERE start_ts >= ? AND start_ts < ?"
        f" AND sport IN ({run_placeholders})",
        (start, end_exclusive, *RUN_SPORTS),
    ).fetchone()

    strength_row = conn.execute(
        f"SELECT COUNT(*) AS n FROM activities"
        f" WHERE start_ts >= ? AND start_ts < ?"
        f" AND sport IN ({strength_placeholders})",
        (start, end_exclusive, *STRENGTH_SPORTS),
    ).fetchone()

    load_row = conn.execute(
        "SELECT COALESCE(SUM(COALESCE(training_load, 0)), 0) AS load"
        " FROM activities WHERE start_ts >= ? AND start_ts < ?",
        (start, end_exclusive),
    ).fetchone()

    sleep_row = conn.execute(
        "SELECT AVG(total_sleep_s) AS avg_s FROM sleep"
        " WHERE date >= ? AND date <= ? AND total_sleep_s IS NOT NULL",
        (start, sunday.isoformat()),
    ).fetchone()

    sleep_avg_s = sleep_row["avg_s"] if sleep_row["avg_s"] is not None else 0.0

    return {
        "runs": float(runs_row["n"]),
        "run_distance_km": float(runs_row["dist"]) / 1000.0,
        "long_run_km": float(runs_row["longest"]) / 1000.0,
        "strength_sessions": float(strength_row["n"]),
        "sleep_hours_avg": float(sleep_avg_s) / 3600.0,
        "weekly_load_target": float(load_row["load"]),
    }


def _score_target(name: str, planned: float, actual: float) -> TargetScore:
    if name in COUNT_TARGETS:
        score = _score_count(planned, actual)
    elif name in AT_LEAST_TARGETS:
        # Sleeping more than planned is fine, never penalise.
        penalise_over = name != "sleep_hours_avg"
        score = _score_at_least(planned, actual, penalise_over=penalise_over)
    else:  # pragma: no cover - defensive, schema constrains the set
        score = 100.0
    return TargetScore(
        target=name,
        planned=planned,
        actual=actual,
        score=score,
        delta=actual - planned,
    )


def score_week(
    conn: sqlite3.Connection,
    plan: Plan,
    *,
    iso_year: int,
    iso_week: int,
) -> WeeklyAdherence:
    """Compute adherence for one ISO week against ``plan.weekly_targets``."""
    monday, sunday = _iso_week_bounds(iso_year, iso_week)
    actuals = _collect_actuals(conn, monday, sunday)

    targets: WeeklyTargets = plan.weekly_targets
    scored: list[TargetScore] = []
    for name in WEIGHTS:
        planned = getattr(targets, name)
        if planned is None:
            continue
        scored.append(_score_target(name, float(planned), actuals[name]))

    if not scored:
        return WeeklyAdherence(
            iso_year=iso_year,
            iso_week=iso_week,
            overall_score=100.0,
            target_scores=[],
            misses=[],
        )

    weight_sum = sum(WEIGHTS[t.target] for t in scored)
    overall = sum(t.score * WEIGHTS[t.target] for t in scored) / weight_sum

    misses = [
        f"{t.target}: planned {t.planned:g}, actual {t.actual:.2f} (score {t.score:.0f})"
        for t in scored
        if t.score < MISS_THRESHOLD
    ]

    return WeeklyAdherence(
        iso_year=iso_year,
        iso_week=iso_week,
        overall_score=overall,
        target_scores=scored,
        misses=misses,
    )
