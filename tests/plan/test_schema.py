"""Tests for the plan.yaml Pydantic schema."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from health.plan.schema import Plan

CANONICAL: dict[str, object] = {
    "athlete": {
        "name": "Your Name",
        "resting_hr": 55,
        "max_hr": 185,
        "weight_kg": 70,
    },
    "context": {
        "goal": "Build aerobic base; lose 3kg over 12 weeks",
        "constraints": "Knees flare up past 60min running",
    },
    "weekly_targets": {
        "runs": 3,
        "run_distance_km": 25,
        "strength_sessions": 1,
        "long_run_km": 10,
        "sleep_hours_avg": 7.5,
        "weekly_load_target": 350,
    },
    "events": [
        {
            "name": "Local 10K",
            "date": "2026-08-15",
            "priority": "B",
            "target_time": "00:50:00",
        }
    ],
}


def test_canonical_example_validates() -> None:
    plan = Plan.model_validate(CANONICAL)
    assert plan.athlete.name == "Your Name"
    assert plan.weekly_targets.runs == 3
    assert plan.events[0].date == date(2026, 8, 15)


def test_rejects_max_hr_le_resting_hr() -> None:
    payload = {
        "athlete": {"name": "X", "resting_hr": 180, "max_hr": 170},
    }
    with pytest.raises(ValidationError):
        Plan.model_validate(payload)


def test_rejects_max_hr_out_of_range() -> None:
    payload = {
        "athlete": {"name": "X", "resting_hr": 55, "max_hr": 300},
    }
    with pytest.raises(ValidationError):
        Plan.model_validate(payload)


def test_event_date_string_is_coerced() -> None:
    payload = {
        "athlete": {"name": "X", "resting_hr": 55, "max_hr": 185},
        "events": [{"name": "Race", "date": "2026-12-01"}],
    }
    plan = Plan.model_validate(payload)
    assert plan.events[0].date == date(2026, 12, 1)
