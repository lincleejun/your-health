"""Orchestrates per-day Garmin pulls into the health DB.

The runner iterates a date range, validates each Garmin payload through the
Pydantic models, and upserts via :mod:`health.ingest.store`. Per-day errors are
isolated so one bad day cannot abort the whole run, and each day commits in
its own transaction so a later crash doesn't roll back earlier progress.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from health.db.conn import transaction
from health.ingest.garmin import DayBundle, GarminClient
from health.ingest.models import (
    Activity,
    BodyComposition,
    DailySummary,
    HrvDay,
    Sleep,
)
from health.ingest.store import (
    record_ingest_run,
    upsert_activity,
    upsert_body_composition,
    upsert_daily_summary,
    upsert_hrv,
    upsert_sleep,
)

log = logging.getLogger(__name__)


@dataclass
class IngestSummary:
    run_id: int
    days_requested: int
    rows_written: int
    errors: list[str]
    started_at: datetime
    finished_at: datetime


def _iter_dates(start: date, end: date) -> list[date]:
    span = (end - start).days
    return [start + timedelta(days=i) for i in range(span + 1)]


def _write_bundle(conn: sqlite3.Connection, bundle: DayBundle) -> int:
    """Persist all non-None fields of a DayBundle. Returns row count written.

    Each model's ``from_garmin`` may return ``None`` when Garmin reported no
    data for the day — we simply skip those.
    """
    written = 0
    d = bundle.date
    if (
        bundle.summary is not None
        and (m := DailySummary.from_garmin(bundle.summary, for_date=d)) is not None
    ):
        upsert_daily_summary(conn, m)
        written += 1
    if bundle.sleep is not None and (s := Sleep.from_garmin(bundle.sleep, for_date=d)) is not None:
        upsert_sleep(conn, s)
        written += 1
    if bundle.hrv is not None and (h := HrvDay.from_garmin(bundle.hrv, for_date=d)) is not None:
        upsert_hrv(conn, h)
        written += 1
    if (
        bundle.body_composition is not None
        and (b := BodyComposition.from_garmin(bundle.body_composition, for_date=d)) is not None
    ):
        upsert_body_composition(conn, b)
        written += 1
    return written


def _ingest_one_day(conn: sqlite3.Connection, client: GarminClient, d: date) -> int:
    bundle = client.fetch_day(d)
    with transaction(conn):
        return _write_bundle(conn, bundle)


def _ingest_activities(
    conn: sqlite3.Connection,
    client: GarminClient,
    start: date,
    end: date,
    errors: list[str],
) -> int:
    try:
        items: list[dict[str, Any]] = client.fetch_activities(start, end)
    except Exception as exc:
        log.warning("activities fetch failed: %s", exc, exc_info=True)
        errors.append(f"activities: {exc}")
        return 0
    written = 0
    with transaction(conn):
        for item in items:
            upsert_activity(conn, Activity.from_garmin(item))
            written += 1
    return written


def ingest_range(
    conn: sqlite3.Connection,
    client: GarminClient,
    start: date,
    end: date,
) -> IngestSummary:
    """Pull a date range from Garmin into the DB. One bad day never aborts."""
    started_at = datetime.now(UTC)
    dates = _iter_dates(start, end)
    days_requested = len(dates)
    rows_written = 0
    errors: list[str] = []

    for d in dates:
        try:
            rows_written += _ingest_one_day(conn, client, d)
        except Exception as exc:
            log.warning("ingest day %s failed: %s", d.isoformat(), exc, exc_info=True)
            errors.append(f"{d.isoformat()}: {exc}")

    rows_written += _ingest_activities(conn, client, start, end, errors)

    error_text = "; ".join(errors) if errors else None
    with transaction(conn):
        run_id = record_ingest_run(
            conn,
            days_requested=days_requested,
            rows_written=rows_written,
            error=error_text,
        )

    finished_at = datetime.now(UTC)
    return IngestSummary(
        run_id=run_id,
        days_requested=days_requested,
        rows_written=rows_written,
        errors=errors,
        started_at=started_at,
        finished_at=finished_at,
    )
