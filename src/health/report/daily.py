"""Daily Markdown report card.

Pure DB reader: given a connection and a day, returns a Markdown string.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from health.metrics.physiology import PhysiologySeries, TrendPoint, compute_physiology_series
from health.report.render import (
    render_kpi_table,
    render_section,
    render_trend_bullet,
)

NO_DATA = "_no data_"


def _fmt_or_dash(value: float | None, *, precision: int = 1, unit: str = "") -> str:
    if value is None:
        return "–"  # noqa: RUF001 reason: en-dash missing-value glyph
    body = f"{value:.{precision}f}"
    return f"{body} {unit}" if unit else body


def _activity_body(conn: sqlite3.Connection, day: date) -> str:
    next_day = day + timedelta(days=1)
    rows = conn.execute(
        "SELECT sport, duration_s, distance_m, avg_hr FROM activities "
        "WHERE start_ts >= ? AND start_ts < ?",
        (f"{day.isoformat()}T00:00:00", f"{next_day.isoformat()}T00:00:00"),
    ).fetchall()
    if not rows:
        return NO_DATA

    by_sport: dict[str, dict[str, float]] = {}
    for row in rows:
        sport = row["sport"] or "unknown"
        agg = by_sport.setdefault(sport, {"dist_km": 0.0, "dur_h": 0.0, "n": 0.0})
        agg["dist_km"] += (row["distance_m"] or 0.0) / 1000.0
        agg["dur_h"] += (row["duration_s"] or 0.0) / 3600.0
        agg["n"] += 1

    table: list[tuple[str, str]] = []
    for sport, agg in sorted(by_sport.items()):
        table.append(
            (
                sport,
                f"{int(agg['n'])} act, {agg['dist_km']:.1f} km, {agg['dur_h']:.2f} h",
            )
        )
    return render_kpi_table(table)


def _sleep_body(conn: sqlite3.Connection, day: date) -> str:
    row = conn.execute(
        "SELECT total_sleep_s, deep_s, light_s, rem_s, awake_s, sleep_score "
        "FROM sleep WHERE date = ?",
        (day.isoformat(),),
    ).fetchone()
    if row is None:
        return NO_DATA
    total = row["total_sleep_s"]
    hours = None if total is None else total / 3600.0
    rows: list[tuple[str, str]] = [
        ("total", _fmt_or_dash(hours, precision=1, unit="h")),
        ("sleep score", _fmt_or_dash(row["sleep_score"], precision=0)),
    ]
    return render_kpi_table(rows)


def _physiology_body(conn: sqlite3.Connection, day: date) -> str:
    row = conn.execute(
        "SELECT resting_hr, body_battery_min, body_battery_max FROM daily_summary WHERE date = ?",
        (day.isoformat(),),
    ).fetchone()
    hrv_row = conn.execute(
        "SELECT weekly_avg FROM hrv WHERE date = ?", (day.isoformat(),)
    ).fetchone()
    if row is None and hrv_row is None:
        return NO_DATA
    rhr = row["resting_hr"] if row is not None else None
    bb_min = row["body_battery_min"] if row is not None else None
    bb_max = row["body_battery_max"] if row is not None else None
    hrv = hrv_row["weekly_avg"] if hrv_row is not None else None
    bb_min_f = None if bb_min is None else float(bb_min)
    bb_max_f = None if bb_max is None else float(bb_max)
    rows: list[tuple[str, str]] = [
        ("RHR", _fmt_or_dash(rhr, precision=1, unit="bpm")),
        ("HRV (weekly avg)", _fmt_or_dash(hrv, precision=1, unit="ms")),
        ("body battery min", _fmt_or_dash(bb_min_f, precision=0)),
        ("body battery max", _fmt_or_dash(bb_max_f, precision=0)),
    ]
    return render_kpi_table(rows)


def _last_point(points: list[TrendPoint]) -> TrendPoint | None:
    return points[-1] if points else None


def _has_signal(tp: TrendPoint | None) -> bool:
    if tp is None:
        return False
    return tp.value is not None or tp.mean_7d is not None or tp.mean_28d is not None


def _trend_body(series: PhysiologySeries) -> str:
    rhr = _last_point(series.resting_hr)
    hrv = _last_point(series.hrv_weekly_avg)
    sleep = _last_point(series.sleep_total_hours)
    if not (_has_signal(rhr) or _has_signal(hrv) or _has_signal(sleep)):
        return NO_DATA
    lines: list[str] = []
    if rhr is not None:
        lines.append(render_trend_bullet("RHR", rhr.value, rhr.mean_7d, rhr.mean_28d, unit="bpm"))
    if hrv is not None:
        lines.append(render_trend_bullet("HRV", hrv.value, hrv.mean_7d, hrv.mean_28d, unit="ms"))
    if sleep is not None:
        lines.append(
            render_trend_bullet("Sleep", sleep.value, sleep.mean_7d, sleep.mean_28d, unit="h")
        )
    return "\n".join(lines)


def render_daily_report(conn: sqlite3.Connection, *, day: date) -> str:
    """Return a Markdown report for a single ``day``.

    Sections always render — empty ones show ``_no data_``.
    """
    series = compute_physiology_series(conn, start=day - timedelta(days=7), end=day)
    parts: list[str] = [
        render_section(f"Daily report — {day.isoformat()}", "", level=1).rstrip() + "\n",
        render_section("Activity", _activity_body(conn, day)),
        render_section("Sleep", _sleep_body(conn, day)),
        render_section("Physiology (RHR, HRV, body battery)", _physiology_body(conn, day)),
        render_section("Trend vs 7-day average", _trend_body(series)),
    ]
    return "\n".join(parts)
