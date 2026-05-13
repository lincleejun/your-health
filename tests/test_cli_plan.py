"""Tests for ``health plan check``."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from health.cli import app
from health.plan.adherence import TargetScore, WeeklyAdherence

PLAN_YAML = """\
athlete:
  name: Test
  resting_hr: 50
  max_hr: 190
weekly_targets:
  runs: 4
  run_distance_km: 40
"""


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def plan_file(tmp_path: Path) -> Path:
    p = tmp_path / "plan.yaml"
    p.write_text(PLAN_YAML)
    return p


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "health.db"


def _make_result(misses: list[str] | None = None) -> WeeklyAdherence:
    return WeeklyAdherence(
        iso_year=2025,
        iso_week=3,
        overall_score=82.5,
        target_scores=[
            TargetScore(target="runs", planned=4, actual=3, score=75.0, delta=-1.0),
            TargetScore(
                target="run_distance_km",
                planned=40,
                actual=42.0,
                score=100.0,
                delta=2.0,
            ),
        ],
        misses=misses if misses is not None else [],
    )


@pytest.fixture
def patch_score(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, object]]:
    captured: dict[str, object] = {}

    def fake(conn: object, plan: object, *, iso_year: int, iso_week: int) -> WeeklyAdherence:
        captured["iso_year"] = iso_year
        captured["iso_week"] = iso_week
        captured["plan"] = plan
        result = captured.get("_result")
        if isinstance(result, WeeklyAdherence):
            return result
        return _make_result()

    monkeypatch.setattr("health.plan.adherence.score_week", fake)
    yield captured


def test_happy_path(
    runner: CliRunner,
    plan_file: Path,
    db_path: Path,
    patch_score: dict[str, object],
) -> None:
    result = runner.invoke(
        app,
        [
            "plan",
            "check",
            "--week",
            "2025-W03",
            "--plan",
            str(plan_file),
            "--db",
            str(db_path),
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert "Overall:" in result.stdout
    assert "82.5" in result.stdout
    assert "runs" in result.stdout
    assert "run_distance_km" in result.stdout
    assert patch_score["iso_year"] == 2025
    assert patch_score["iso_week"] == 3


def test_missing_plan_exits_one(runner: CliRunner, tmp_path: Path, db_path: Path) -> None:
    missing = tmp_path / "does_not_exist.yaml"
    result = runner.invoke(
        app,
        [
            "plan",
            "check",
            "--week",
            "2025-W03",
            "--plan",
            str(missing),
            "--db",
            str(db_path),
        ],
    )
    assert result.exit_code == 1
    assert "plan file not found" in result.stderr


@pytest.mark.parametrize("bad", ["2025-03", "2025W03", "25-W03", "2025-W3", "garbage"])
def test_bad_week_format(runner: CliRunner, plan_file: Path, db_path: Path, bad: str) -> None:
    result = runner.invoke(
        app,
        [
            "plan",
            "check",
            "--week",
            bad,
            "--plan",
            str(plan_file),
            "--db",
            str(db_path),
        ],
    )
    assert result.exit_code != 0


def test_misses_printed(
    runner: CliRunner,
    plan_file: Path,
    db_path: Path,
    patch_score: dict[str, object],
) -> None:
    patch_score["_result"] = _make_result(
        misses=[
            "runs: planned 4, actual 2.00 (score 50)",
            "long_run_km: planned 18, actual 10.00 (score 55)",
        ]
    )
    result = runner.invoke(
        app,
        [
            "plan",
            "check",
            "--week",
            "2025-W03",
            "--plan",
            str(plan_file),
            "--db",
            str(db_path),
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert "Misses: 2" in result.stdout
    assert "runs: planned 4" in result.stdout
    assert "long_run_km: planned 18" in result.stdout
