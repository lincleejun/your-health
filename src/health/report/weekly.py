"""Weekly Markdown dashboard.

Computes one ISO week of training load, activity volume, HR zone distribution,
physiology trends, and anomaly bullets. Pure DB reader.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from health.metrics.activity import (
    WeeklyVolume,
    ZoneDistribution,
    compute_weekly_volume,
    compute_zone_distribution,
)
from health.metrics.load import LoadPoint, compute_load_series
from health.metrics.physiology import PhysiologySeries, TrendPoint, compute_physiology_series
from health.report.render import (
    render_kpi_table,
    render_section,
    render_trend_bullet,
)

NO_DATA = "_no data_"

# TODO(report-04): plan-driven HR thresholds. Until then use generic defaults.
_DEFAULT_MAX_HR = 185
_DEFAULT_RESTING_HR = 55


def _fmt(value: float | None, *, precision: int = 1) -> str:
    if value is None:
        return "–"  # noqa: RUF001 reason: en-dash missing-value glyph
    return f"{value:.{precision}f}"


def _load_body(points: list[LoadPoint]) -> str:
    if not points:
        return NO_DATA
    last = points[-1]
    rows: list[tuple[str, str]] = [
        ("CTL (end of week)", _fmt(last.ctl)),
        ("ATL (end of week)", _fmt(last.atl)),
        ("ACWR", _fmt(last.acwr, precision=2)),
    ]
    return render_kpi_table(rows)


def _volume_body(weeks: list[WeeklyVolume]) -> str:
    if not weeks:
        return NO_DATA
    week = weeks[0]
    rows: list[tuple[str, str]] = [
        ("total distance", f"{week.total_distance_km:.1f} km"),
        ("total duration", f"{week.total_duration_h:.2f} h"),
        ("activities", str(week.total_activities)),
    ]
    for sport, sv in sorted(week.by_sport.items()):
        rows.append(
            (
                f"  {sport}",
                f"{sv.activities} act, {sv.distance_km:.1f} km, {sv.duration_h:.2f} h",
            )
        )
    return render_kpi_table(rows)


def _zone_body(zd: ZoneDistribution) -> str:
    if zd.total_seconds <= 0:
        return NO_DATA
    rows: list[tuple[str, str]] = []
    for zone in range(1, 6):
        secs = zd.zone_seconds.get(zone, 0.0)
        hours = secs / 3600.0
        pct = (secs / zd.total_seconds) * 100.0 if zd.total_seconds > 0 else 0.0
        rows.append((f"Zone {zone}", f"{hours:.2f} h ({pct:.0f}%)"))
    return render_kpi_table(rows)


def _last_in_week(points: list[TrendPoint], week_end: date) -> TrendPoint | None:
    for tp in reversed(points):
        if tp.date <= week_end:
            return tp
    return None


def _physiology_body(series: PhysiologySeries, week_end: date) -> str:
    rhr = _last_in_week(series.resting_hr, week_end)
    hrv = _last_in_week(series.hrv_weekly_avg, week_end)
    sleep = _last_in_week(series.sleep_total_hours, week_end)
    has_any = any(
        tp is not None
        and (tp.value is not None or tp.mean_7d is not None or tp.mean_28d is not None)
        for tp in (rhr, hrv, sleep)
    )
    if not has_any:
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


def _anomalies_body(series: PhysiologySeries, week_start: date, week_end: date) -> str:
    bullets: list[str] = []
    for label, points in (
        ("RHR", series.resting_hr),
        ("HRV", series.hrv_weekly_avg),
        ("Sleep", series.sleep_total_hours),
    ):
        for tp in points:
            if week_start <= tp.date <= week_end and tp.is_anomaly:
                z = _fmt(tp.z_score_28d, precision=2)
                bullets.append(f"- {tp.date.isoformat()} **{label}** z={z}")
    if not bullets:
        return NO_DATA
    return "\n".join(bullets)


def render_weekly_report(conn: sqlite3.Connection, *, iso_year: int, iso_week: int) -> str:
    """Return a Markdown report for one ISO week."""
    week_start = date.fromisocalendar(iso_year, iso_week, 1)
    week_end = week_start + timedelta(days=6)

    load = compute_load_series(conn, start=week_start, end=week_end)
    volume = compute_weekly_volume(conn, start=week_start, end=week_end)
    zones = compute_zone_distribution(
        conn,
        start=week_start,
        end=week_end,
        max_hr=_DEFAULT_MAX_HR,
        resting_hr=_DEFAULT_RESTING_HR,
    )
    series = compute_physiology_series(conn, start=week_start, end=week_end)

    parts: list[str] = [
        render_section(f"Weekly report — {iso_year}-W{iso_week:02d}", "", level=1).rstrip() + "\n",
        render_section("Training load (CTL/ATL/ACWR end-of-week)", _load_body(load)),
        render_section("Activity volume (total km, hours, by sport)", _volume_body(volume)),
        render_section("HR zone distribution", _zone_body(zones)),
        render_section(
            "Physiology trends (RHR, HRV, sleep — 7d + 28d, flagged anomalies)",
            _physiology_body(series, week_end),
        ),
        render_section("Anomalies of the week", _anomalies_body(series, week_start, week_end)),
    ]
    return "\n".join(parts)
