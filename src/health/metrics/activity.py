"""Activity-derived metrics: weekly volume and HR zone distribution.

Reads from the ``activities`` table. All dates are interpreted in UTC — the
``start_ts`` column is an ISO 8601 timestamp stored as UTC by the ingest layer,
so week boundaries are computed against the UTC calendar date.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

# Karvonen HR-reserve zone bounds. Lower bound inclusive, upper bound exclusive,
# except Zone 5 which is inclusive at 1.0.
_ZONE_BOUNDS: tuple[tuple[int, float, float], ...] = (
    (1, 0.50, 0.60),
    (2, 0.60, 0.70),
    (3, 0.70, 0.80),
    (4, 0.80, 0.90),
    (5, 0.90, 1.00),
)


@dataclass(frozen=True)
class SportVolume:
    sport: str
    distance_km: float
    duration_h: float
    activities: int


@dataclass(frozen=True)
class WeeklyVolume:
    iso_year: int
    iso_week: int
    week_start: date
    by_sport: dict[str, SportVolume]
    total_distance_km: float
    total_duration_h: float
    total_activities: int


@dataclass(frozen=True)
class ZoneDistribution:
    zone_seconds: dict[int, float]
    total_seconds: float


def _activity_date_utc(start_ts: str) -> date:
    """Return the UTC calendar date for a stored ``start_ts`` ISO string."""
    dt = datetime.fromisoformat(start_ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).date()


def _monday_of(d: date) -> date:
    return d - timedelta(days=d.isoweekday() - 1)


def compute_weekly_volume(
    conn: sqlite3.Connection,
    *,
    start: date,
    end: date,
) -> list[WeeklyVolume]:
    """One :class:`WeeklyVolume` per ISO week that has at least one activity in
    ``[start, end]``. Sorted ascending by ``week_start``.

    Distance is summed as kilometres (``distance_m / 1000``, NULL treated as 0)
    and duration as hours (``duration_s / 3600``, NULL treated as 0). The sport
    key is the raw ``sport`` column — no remapping.
    """
    rows = conn.execute(
        "SELECT start_ts, sport, duration_s, distance_m "
        "FROM activities "
        "WHERE date(start_ts) BETWEEN ? AND ? "
        "ORDER BY start_ts ASC",
        (start.isoformat(), end.isoformat()),
    ).fetchall()

    # Bucket by (iso_year, iso_week) then by sport.
    buckets: dict[tuple[int, int], dict[str, list[tuple[float, float]]]] = {}
    week_starts: dict[tuple[int, int], date] = {}

    for row in rows:
        d = _activity_date_utc(row["start_ts"])
        iso = d.isocalendar()
        key = (iso.year, iso.week)
        week_starts[key] = _monday_of(d)
        sport = row["sport"] or "unknown"
        dist_km = (row["distance_m"] or 0.0) / 1000.0
        dur_h = (row["duration_s"] or 0.0) / 3600.0
        buckets.setdefault(key, {}).setdefault(sport, []).append((dist_km, dur_h))

    result: list[WeeklyVolume] = []
    for key in sorted(buckets, key=lambda k: week_starts[k]):
        sport_map: dict[str, SportVolume] = {}
        total_dist = 0.0
        total_dur = 0.0
        total_acts = 0
        for sport, entries in buckets[key].items():
            sd = sum(e[0] for e in entries)
            sh = sum(e[1] for e in entries)
            sport_map[sport] = SportVolume(
                sport=sport,
                distance_km=sd,
                duration_h=sh,
                activities=len(entries),
            )
            total_dist += sd
            total_dur += sh
            total_acts += len(entries)
        result.append(
            WeeklyVolume(
                iso_year=key[0],
                iso_week=key[1],
                week_start=week_starts[key],
                by_sport=sport_map,
                total_distance_km=total_dist,
                total_duration_h=total_dur,
                total_activities=total_acts,
            )
        )
    return result


def _classify_zone(avg_hr: float, max_hr: int, resting_hr: int) -> int:
    """Karvonen HR-reserve classifier. Clamps below zone 1 and above zone 5."""
    reserve = max_hr - resting_hr
    if reserve <= 0:
        return 1
    frac = (avg_hr - resting_hr) / reserve
    if frac < _ZONE_BOUNDS[0][1]:
        return 1
    if frac >= _ZONE_BOUNDS[-1][2]:
        return 5
    for zone, lo, hi in _ZONE_BOUNDS:
        if lo <= frac < hi:
            return zone
    return 5  # pragma: no cover - exhaustive above


def compute_zone_distribution(
    conn: sqlite3.Connection,
    *,
    start: date,
    end: date,
    max_hr: int,
    resting_hr: int,
) -> ZoneDistribution:
    """Aggregate time-in-zone across activities in ``[start, end]``.

    Approximation: we do not have per-second HR samples, only per-activity
    ``avg_hr`` and ``duration_s``. Each activity is classified into a single
    Karvonen zone based on its average HR, then its full duration is attributed
    to that zone. Activities with NULL ``avg_hr`` or NULL ``duration_s`` are
    ignored. Dates are interpreted in UTC.
    """
    rows = conn.execute(
        "SELECT avg_hr, duration_s FROM activities "
        "WHERE date(start_ts) BETWEEN ? AND ? "
        "AND avg_hr IS NOT NULL AND duration_s IS NOT NULL",
        (start.isoformat(), end.isoformat()),
    ).fetchall()

    zone_seconds: dict[int, float] = {}
    total = 0.0
    for row in rows:
        zone = _classify_zone(float(row["avg_hr"]), max_hr, resting_hr)
        secs = float(row["duration_s"])
        zone_seconds[zone] = zone_seconds.get(zone, 0.0) + secs
        total += secs
    return ZoneDistribution(zone_seconds=zone_seconds, total_seconds=total)
