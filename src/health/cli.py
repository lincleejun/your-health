"""Health CLI — entry point wired via ``[project.scripts] health = "health.cli:app"``."""

from __future__ import annotations

import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from health.db.conn import connect, initialize
from health.ingest.garmin import GarminClient, GarminLoginError
from health.plan.loader import PlanLoadError, load_plan

# reason: runner.py lives in a sibling worktree; keep IngestSummary Any.
IngestSummary = Any

app = typer.Typer(help="Personal health data CLI.", no_args_is_help=True)


@app.callback()
def _main() -> None:
    """Anchor the Typer app so single-subcommand layout doesn't collapse."""


_DEFAULT_DB = Path("./data/health.db")
_DEFAULT_TOKEN_DIR = Path("./config/.garmin_tokens")
_DEFAULT_PLAN = Path("./config/plan.yaml")
_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")
plan_app = typer.Typer(help="Plan tools.", no_args_is_help=True)
app.add_typer(plan_app, name="plan")


def _parse_iso_week(value: str) -> tuple[int, int]:
    m = _WEEK_RE.match(value)
    if not m:
        raise typer.BadParameter("--week must look like 'YYYY-Www' (e.g. 2025-W03)")
    year, week = int(m.group(1)), int(m.group(2))
    try:
        date.fromisocalendar(year, week, 1)
    except ValueError as exc:
        raise typer.BadParameter(f"--week: {exc}") from exc
    return year, week


@plan_app.command("check")
def plan_check(
    week: str = typer.Option(..., "--week", help="ISO week YYYY-Www (e.g. 2025-W03)."),
    plan: Path = typer.Option(_DEFAULT_PLAN, "--plan", help="Path to plan.yaml."),  # noqa: B008
    db: Path = typer.Option(_DEFAULT_DB, "--db", help="SQLite database path."),  # noqa: B008
) -> None:
    """Score adherence for one ISO week against the plan's weekly targets."""
    iso_year, iso_week = _parse_iso_week(week)

    try:
        plan_obj = load_plan(Path(plan))
    except PlanLoadError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    try:
        conn = connect(db)
        initialize(conn)
    except Exception as exc:
        typer.echo(f"Failed to initialise database at {db}: {exc}", err=True)
        raise typer.Exit(1) from exc

    # reason: importlib lets tests monkeypatch ``score_week`` post-import.
    import importlib

    score_fn = importlib.import_module("health.plan.adherence").score_week
    result = score_fn(conn, plan_obj, iso_year=iso_year, iso_week=iso_week)

    console = Console()
    title = f"Adherence {iso_year}-W{iso_week:02d}"
    table = Table(title=title, show_header=True, header_style="bold")
    for col in ("target", "planned", "actual", "score", "delta"):
        table.add_column(col)
    for ts in result.target_scores:
        row = (
            ts.target,
            f"{ts.planned:g}",
            f"{ts.actual:.2f}",
            f"{ts.score:.0f}",
            f"{ts.delta:+.2f}",
        )
        table.add_row(*row)
    console.print(table)
    console.print(f"Overall: {result.overall_score:.1f}/100")
    console.print(f"Misses: {len(result.misses)}")
    for miss in result.misses[:5]:
        console.print(f"  - {miss}")


def _load_env() -> None:
    """Load ``config/.env`` first (preferred), then fall back to ``.env``."""
    if Path("config/.env").is_file():
        load_dotenv(Path("config/.env"))
    if Path(".env").is_file():
        load_dotenv(Path(".env"), override=False)


def _resolve_range(days: int, start: date | None) -> tuple[date, date]:
    if days < 1:
        raise typer.BadParameter("--days must be >= 1")
    if start is not None:
        return start, start + timedelta(days=days - 1)
    end = date.today()
    return end - timedelta(days=days - 1), end


def _render_summary(summary: IngestSummary, elapsed: float, start_d: date, end_d: date) -> None:
    console = Console()
    table = Table(title="Garmin ingest summary", show_header=True, header_style="bold")
    table.add_column("field")
    table.add_column("value")
    for k, v in (
        ("run_id", str(summary.run_id)),
        ("range", f"{start_d.isoformat()}..{end_d.isoformat()}"),
        ("days_requested", str(summary.days_requested)),
        ("rows_written", str(summary.rows_written)),
        ("errors", str(len(summary.errors))),
        ("started_at", summary.started_at.isoformat(timespec="seconds")),
        ("finished_at", summary.finished_at.isoformat(timespec="seconds")),
        ("elapsed_seconds", f"{elapsed:.2f}"),
    ):
        table.add_row(k, v)
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
    except GarminLoginError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    except Exception as exc:
        typer.echo(f"Garmin login failed: {exc}", err=True)
        raise typer.Exit(1) from exc

    # reason: inline import lets tests monkeypatch ``ingest_range``.
    import importlib

    ingest_range = importlib.import_module("health.ingest.runner").ingest_range

    t0 = time.monotonic()
    summary = ingest_range(conn, client, start_d, end_d)
    elapsed = time.monotonic() - t0
    _render_summary(summary, elapsed, start_d, end_d)


if __name__ == "__main__":  # pragma: no cover
    app()
