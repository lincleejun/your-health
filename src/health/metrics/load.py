"""Training-load metrics: CTL, ATL, and ACWR.

The model is the standard "TrainingPeaks" exponential-weighted moving average
of daily training load:

    CTL_today = CTL_yesterday + (daily_load - CTL_yesterday) / 42
    ATL_today = ATL_yesterday + (daily_load - ATL_yesterday) / 7
    ACWR      = ATL / CTL   (None when CTL <= 0)

To get reasonable values near the start of the requested window we also pull
activities from ``start - 42 days`` and seed CTL=ATL=0 on that earlier day,
running the recurrence across the whole window. Only points in
``[start, end]`` are returned.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

CTL_TAU = 42
ATL_TAU = 7
WARMUP_DAYS = 42


@dataclass(frozen=True)
class LoadPoint:
    """One day of training-load state."""

    date: date
    daily_load: float
    ctl: float
    atl: float
    acwr: float | None


def _fetch_daily_loads(
    conn: sqlite3.Connection,
    *,
    start: date,
    end: date,
) -> dict[date, float]:
    """Return the summed ``training_load`` per day in ``[start, end]``.

    NULL ``training_load`` is coalesced to 0 in SQL. Days with no activities
    do not appear in the returned dict — the caller fills them with 0.
    """
    rows = conn.execute(
        """
        SELECT date(start_ts) AS day,
               SUM(COALESCE(training_load, 0)) AS load
        FROM activities
        WHERE date(start_ts) BETWEEN ? AND ?
        GROUP BY date(start_ts)
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    loads: dict[date, float] = {}
    for row in rows:
        # Rows may be sqlite3.Row or plain tuples depending on row_factory.
        day_str = row[0] if not isinstance(row, sqlite3.Row) else row["day"]
        load = row[1] if not isinstance(row, sqlite3.Row) else row["load"]
        loads[date.fromisoformat(day_str)] = float(load or 0.0)
    return loads


def compute_load_series(
    conn: sqlite3.Connection,
    *,
    start: date,
    end: date,
) -> list[LoadPoint]:
    """Return one :class:`LoadPoint` per date in ``[start, end]`` inclusive.

    Days with no activities still get a point (``daily_load=0``). A 42-day
    warm-up window before ``start`` is read from the database so the EWMA at
    ``start`` reflects recent history rather than a cold zero.
    """
    if end < start:
        return []

    warmup_start = start - timedelta(days=WARMUP_DAYS)
    loads = _fetch_daily_loads(conn, start=warmup_start, end=end)

    points: list[LoadPoint] = []
    ctl = 0.0
    atl = 0.0
    day = warmup_start
    while day <= end:
        daily = loads.get(day, 0.0)
        ctl = ctl + (daily - ctl) / CTL_TAU
        atl = atl + (daily - atl) / ATL_TAU
        if day >= start:
            acwr = atl / ctl if ctl > 0 else None
            points.append(LoadPoint(date=day, daily_load=daily, ctl=ctl, atl=atl, acwr=acwr))
        day += timedelta(days=1)
    return points
