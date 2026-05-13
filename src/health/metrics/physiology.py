"""Physiology trend metrics: 7d / 28d rolling means and z-score anomalies.

For each day in the requested ``[start, end]`` range, we emit one
:class:`TrendPoint` per metric (resting HR, HRV weekly average, sleep total
hours). The rolling window **includes** the current day. To make the very
first day's 28d window meaningful, the loader reads 28 days of history
before ``start`` (the "warm-up window") in addition to the requested range.

Rules:
- ``value`` is the raw reading; ``None`` if the row is missing or NULL.
- Rolling means skip ``None`` readings (do not treat them as 0).
- 7d mean requires >= 2 non-None readings in the trailing 7-day window.
- 28d stats require >= 4 non-None readings; std is the sample (n-1) stdev.
- ``is_anomaly`` is True iff ``abs(z_score_28d) > 1``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, stdev

WARMUP_DAYS = 28
WINDOW_7D = 7
WINDOW_28D = 28
MIN_7D_READINGS = 2
MIN_28D_READINGS = 4


@dataclass(frozen=True)
class TrendPoint:
    date: date
    value: float | None
    mean_7d: float | None
    mean_28d: float | None
    z_score_28d: float | None
    is_anomaly: bool


@dataclass(frozen=True)
class PhysiologySeries:
    resting_hr: list[TrendPoint]
    hrv_weekly_avg: list[TrendPoint]
    sleep_total_hours: list[TrendPoint]


def _load_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    start: date,
    end: date,
) -> dict[date, float | None]:
    rows = conn.execute(
        f"SELECT date, {column} AS v FROM {table} WHERE date >= ? AND date <= ?",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    out: dict[date, float | None] = {}
    for row in rows:
        raw = row["v"]
        out[date.fromisoformat(row["date"])] = None if raw is None else float(raw)
    return out


def _window_stats(
    readings: list[float],
    *,
    min_count: int,
    with_std: bool,
) -> tuple[float | None, float | None]:
    """Return (mean, std) over readings, honouring min_count.

    If ``with_std`` is False, std is always None (caller doesn't need it).
    """
    if len(readings) < min_count:
        return None, None
    m = mean(readings)
    if not with_std:
        return m, None
    if len(readings) < 2:
        return m, None
    s = stdev(readings)
    return m, s


def _compute_series(
    values_by_date: dict[date, float | None],
    start: date,
    end: date,
) -> list[TrendPoint]:
    points: list[TrendPoint] = []
    span = (end - start).days
    for offset in range(span + 1):
        today = start + timedelta(days=offset)
        value = values_by_date.get(today)

        window_7 = [
            v
            for d in range(WINDOW_7D)
            if (v := values_by_date.get(today - timedelta(days=d))) is not None
        ]
        window_28 = [
            v
            for d in range(WINDOW_28D)
            if (v := values_by_date.get(today - timedelta(days=d))) is not None
        ]

        mean_7d, _ = _window_stats(window_7, min_count=MIN_7D_READINGS, with_std=False)
        mean_28d, std_28d = _window_stats(window_28, min_count=MIN_28D_READINGS, with_std=True)

        z: float | None = None
        anomaly = False
        if value is not None and mean_28d is not None and std_28d is not None and std_28d > 0:
            z = (value - mean_28d) / std_28d
            anomaly = abs(z) > 1
        elif value is not None and mean_28d is not None and std_28d == 0:
            z = 0.0
            anomaly = False

        points.append(
            TrendPoint(
                date=today,
                value=value,
                mean_7d=mean_7d,
                mean_28d=mean_28d,
                z_score_28d=z,
                is_anomaly=anomaly,
            )
        )
    return points


def compute_physiology_series(
    conn: sqlite3.Connection,
    *,
    start: date,
    end: date,
) -> PhysiologySeries:
    """Emit physiology trend points for ``[start, end]`` inclusive.

    The implementation reads an additional 28-day warm-up window before
    ``start`` so the first emitted point's 28d statistics see real history.
    """
    warmup_start = start - timedelta(days=WARMUP_DAYS)

    rhr = _load_column(conn, "daily_summary", "resting_hr", warmup_start, end)
    hrv = _load_column(conn, "hrv", "weekly_avg", warmup_start, end)
    sleep_raw = _load_column(conn, "sleep", "total_sleep_s", warmup_start, end)
    sleep_hours: dict[date, float | None] = {
        d: (None if v is None else v / 3600.0) for d, v in sleep_raw.items()
    }

    return PhysiologySeries(
        resting_hr=_compute_series(rhr, start, end),
        hrv_weekly_avg=_compute_series(hrv, start, end),
        sleep_total_hours=_compute_series(sleep_hours, start, end),
    )
