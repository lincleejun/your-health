"""Shared helpers for the ``health report`` CLI subcommands.

Kept separate from ``health.cli`` so the CLI module stays small and so tests
can poke at these helpers directly without going through Typer.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import typer
from rich.console import Console

from health.db.conn import connect, initialize

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


def parse_iso_week(value: str) -> tuple[int, int]:
    """Parse an ISO week token ``YYYY-Www``. Raises ``typer.BadParameter``."""
    m = _WEEK_RE.match(value)
    if not m:
        raise typer.BadParameter("--week must be in ISO format YYYY-Www, e.g. 2026-W18")
    year = int(m.group(1))
    week = int(m.group(2))
    if not 1 <= week <= 53:
        raise typer.BadParameter("--week week-of-year must be between 01 and 53")
    return year, week


def open_db(db: Path) -> sqlite3.Connection:
    """Open the DB at ``db`` and apply the schema. Idempotent."""
    try:
        conn = connect(db)
        initialize(conn)
    except Exception as exc:
        typer.echo(f"Failed to initialise database at {db}: {exc}", err=True)
        raise typer.Exit(1) from exc
    return conn


def emit(md: str, out: Path | None) -> None:
    """Write ``md`` to ``out`` (creating parents) or print to stdout."""
    if out is None:
        # reason: markdown can contain Rich markup-like tokens; render literally.
        Console().print(md, markup=False, highlight=False)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    # reason: avoid Rich line-wrapping long tmp paths; write plain text to stderr.
    print(f"Wrote {out}", file=sys.stderr)
