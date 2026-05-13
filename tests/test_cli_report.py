"""Tests for the ``health report`` CLI subcommands."""

from __future__ import annotations

import importlib
import sqlite3
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from health.cli import app
from health.db.conn import connect, initialize


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "health.db"


def _seed_minimum(path: Path, day: date) -> None:
    """Create the DB with schema applied and a single daily_summary row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        initialize(conn)
        conn.execute(
            "INSERT INTO daily_summary(date, resting_hr, raw_json) VALUES (?, ?, '{}')",
            (day.isoformat(), 55.0),
        )
        conn.commit()
    finally:
        conn.close()


def test_report_daily_prints_markdown_to_stdout(runner: CliRunner, db_path: Path) -> None:
    day = date(2026, 4, 29)
    _seed_minimum(db_path, day)
    result = runner.invoke(
        app,
        ["report", "daily", "--date", day.isoformat(), "--db", str(db_path)],
    )
    assert result.exit_code == 0, result.stderr
    assert "# Daily report" in result.stdout


def test_report_daily_writes_file_when_out_given(
    runner: CliRunner, db_path: Path, tmp_path: Path
) -> None:
    day = date(2026, 4, 29)
    _seed_minimum(db_path, day)
    out = tmp_path / "out" / "r.md"
    result = runner.invoke(
        app,
        [
            "report",
            "daily",
            "--date",
            day.isoformat(),
            "--db",
            str(db_path),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert out.is_file()
    text = out.read_text()
    assert "# Daily report" in text
    # The "Wrote <path>" notice goes to stderr.
    assert str(out) in result.stderr


def test_report_weekly_runs_on_seeded_db(runner: CliRunner, db_path: Path) -> None:
    # Empty (but initialised) DB is enough — the weekly renderer prints no-data sections.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        initialize(conn)
        conn.commit()
    finally:
        conn.close()

    result = runner.invoke(
        app,
        ["report", "weekly", "--week", "2026-W18", "--db", str(db_path)],
    )
    assert result.exit_code == 0, result.stderr
    assert "Weekly report" in result.stdout


def test_report_weekly_passes_plan_kwarg(
    runner: CliRunner,
    db_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seed an empty DB.
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        initialize(conn)
        conn.commit()
    finally:
        conn.close()

    plan_yaml = tmp_path / "plan.yaml"
    plan_yaml.write_text(
        """athlete:
  name: "T"
  resting_hr: 55
  max_hr: 185
  weight_kg: 70
context:
  goal: "g"
  constraints: "c"
weekly_targets:
  runs: 3
  run_distance_km: 25
  strength_sessions: 1
  long_run_km: 10
  sleep_hours_avg: 7.5
  weekly_load_target: 350
events: []
"""
    )

    captured: dict[str, object] = {}

    def fake_render(conn: sqlite3.Connection, **kwargs: object) -> str:
        captured["kwargs"] = kwargs
        return "# Weekly report — fake"

    # reason: cli imports render_weekly_report via importlib at call time, so
    # patch the attribute on the imported module.
    weekly_mod = importlib.import_module("health.report.weekly")
    monkeypatch.setattr(weekly_mod, "render_weekly_report", fake_render)

    result = runner.invoke(
        app,
        [
            "report",
            "weekly",
            "--week",
            "2026-W18",
            "--db",
            str(db_path),
            "--plan",
            str(plan_yaml),
        ],
    )
    assert result.exit_code == 0, result.stderr
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["iso_year"] == 2026
    assert kwargs["iso_week"] == 18
    assert "plan" in kwargs
    assert kwargs["plan"] is not None


def test_report_weekly_rejects_bad_week_format(runner: CliRunner, db_path: Path) -> None:
    result = runner.invoke(
        app,
        ["report", "weekly", "--week", "2026-18", "--db", str(db_path)],
    )
    assert result.exit_code != 0
