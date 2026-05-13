"""Tests for the plan.yaml loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from health.plan.loader import PlanLoadError, load_plan

EXAMPLE_PATH = Path(__file__).parents[2] / "config" / "plan.example.yaml"


def test_loads_example_yaml() -> None:
    plan = load_plan(EXAMPLE_PATH)
    assert plan.athlete.name == "Your Name"
    assert plan.weekly_targets.runs == 3
    assert plan.events[0].name == "Local 10K"


def test_missing_file_wrapped(tmp_path: Path) -> None:
    with pytest.raises(PlanLoadError) as exc:
        load_plan(tmp_path / "nope.yaml")
    assert "not found" in str(exc.value).lower() or "missing" in str(exc.value).lower()


def test_bad_yaml_wrapped(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("athlete: [unterminated\n")
    with pytest.raises(PlanLoadError):
        load_plan(bad)


def test_schema_failure_wrapped(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "athlete:\n  name: X\n  resting_hr: 200\n  max_hr: 150\n",
    )
    with pytest.raises(PlanLoadError):
        load_plan(bad)
