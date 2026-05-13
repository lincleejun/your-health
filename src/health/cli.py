"""Health CLI — entry point wired via ``[project.scripts] health = "health.cli:app"``."""

from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from health.db.conn import connect, initialize
from health.ingest.garmin import GarminClient

# reason: sibling worktree owns runner.py; we type IngestSummary as Any to avoid
# importing a module that doesn't yet exist on this branch. The shape is
# documented in PROMPT.md and exercised by tests.
IngestSummary = Any

app = typer.Typer(help="Personal health data CLI.", no_args_is_help=True)


@app.callback()
def _main() -> None:
    """Anchor the Typer app so single-subcommand layout doesn't collapse."""


_DEFAULT_DB = Path("./data/health.db")
_DEFAULT_TOKEN_DIR = Path("./config/.garmin_tokens")


def _load_env() -> None:
    """Load ``config/.env`` first (preferred), then fall back to ``.env``."""
    cfg = Path("config/.env")
    if cfg.is_file():
        load_dotenv(cfg)
    fallback = Path(".env")
    if fallback.is_file():
        load_dotenv(fallback, override=False)


def _resolve_range(days: int, start: date | None) -> tuple[date, date]:
    if days < 1:
        raise typer.BadParameter("--days must be >= 1")
    if start is not None:
        return start, start + timedelta(days=days - 1)
    end = date.today()
    return end - timedelta(days=days - 1), end


def _render_summary(summary: IngestSummary, elapsed: float) -> None:
    console = Console()
    table = Table(title="Garmin ingest summary", show_header=True, header_style="bold")
    table.add_column("field")
    table.add_column("value")

    start_str = summary.started_at.isoformat(timespec="seconds")
    end_str = summary.finished_at.isoformat(timespec="seconds")
    range_str = f"{summary.started_at.date()}..{summary.finished_at.date()}"

    table.add_row("run_id", str(summary.run_id))
    table.add_row("range", range_str)
    table.add_row("days_requested", str(summary.days_requested))
    table.add_row("rows_written", str(summary.rows_written))
    table.add_row("errors", str(len(summary.errors)))
    table.add_row("started_at", start_str)
    table.add_row("finished_at", end_str)
    table.add_row("elapsed_seconds", f"{elapsed:.2f}")
    console.print(table)

    if summary.errors:
        console.print("[bold yellow]First errors:[/bold yellow]")
        for err in summary.errors[:5]:
            console.print(f"  - {err}")


# reason: Typer's idiomatic API requires Option() in defaults; B008 doesn't apply here.
@app.command()
def ingest(
    days: int = typer.Option(..., "--days", help="Number of days to ingest."),
    start: datetime | None = typer.Option(  # noqa: B008
        None,
        "--start",
        formats=["%Y-%m-%d"],
        help="Start date YYYY-MM-DD. Defaults to today - (days-1).",
    ),
    db: Path = typer.Option(_DEFAULT_DB, "--db", help="SQLite database path."),  # noqa: B008
    token_dir: Path = typer.Option(  # noqa: B008
        _DEFAULT_TOKEN_DIR, "--token-dir", help="Where to persist Garmin OAuth tokens."
    ),
) -> None:
    """Ingest the Garmin payloads for the requested date range into SQLite."""
    _load_env()
    email = os.environ.get("GARMIN_EMAIL")
    password = os.environ.get("GARMIN_PASSWORD")
    if not email or not password:
        typer.echo(
            "GARMIN_EMAIL and GARMIN_PASSWORD must be set. "
            "Copy .env.example to config/.env and fill them in.",
            err=True,
        )
        raise typer.Exit(1)

    start_date = start.date() if start is not None else None
    start_d, end_d = _resolve_range(days, start_date)

    try:
        conn = connect(db)
        initialize(conn)
    except Exception as exc:
        typer.echo(f"Failed to initialise database at {db}: {exc}", err=True)
        raise typer.Exit(1) from exc

    try:
        client = GarminClient(email=email, password=password, token_dir=token_dir)
        client.login()
    except Exception as exc:
        typer.echo(f"Garmin login failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    # reason: runner.py lands in a sibling worktree; inline import lets tests
    # monkeypatch ``health.ingest.runner.ingest_range`` and lets this branch
    # compile before the module exists on disk.
    import importlib

    ingest_range = importlib.import_module("health.ingest.runner").ingest_range

    t0 = time.monotonic()
    summary = ingest_range(conn, client, start_d, end_d)
    elapsed = time.monotonic() - t0
    _render_summary(summary, elapsed)


if __name__ == "__main__":  # pragma: no cover
    app()
