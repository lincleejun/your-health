"""Pydantic models for the user's ``plan.yaml`` file.

The schema mirrors ``config/plan.example.yaml``. All fields outside the
athlete block are optional so a minimal plan only needs basic HR anchors.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Athlete(BaseModel):
    name: str
    resting_hr: int = Field(ge=20, le=120)
    max_hr: int = Field(ge=100, le=230)
    weight_kg: float | None = Field(default=None, ge=20, le=400)


class Context(BaseModel):
    goal: str | None = None
    constraints: str | None = None


class WeeklyTargets(BaseModel):
    runs: int | None = Field(default=None, ge=0)
    run_distance_km: float | None = Field(default=None, ge=0)
    strength_sessions: int | None = Field(default=None, ge=0)
    long_run_km: float | None = Field(default=None, ge=0)
    sleep_hours_avg: float | None = Field(default=None, ge=0, le=24)
    weekly_load_target: float | None = Field(default=None, ge=0)


class Event(BaseModel):
    name: str
    date: date
    # "A" | "B" | "C" but not enum-restricted yet — keep the door open for
    # the user to use whatever priority labels they want.
    priority: str | None = None
    target_time: str | None = None  # "HH:MM:SS"


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True)

    athlete: Athlete
    context: Context = Field(default_factory=Context)
    weekly_targets: WeeklyTargets = Field(default_factory=WeeklyTargets)
    events: list[Event] = Field(default_factory=list)

    @model_validator(mode="after")
    def _max_hr_above_resting(self) -> Plan:
        if self.athlete.max_hr <= self.athlete.resting_hr:
            raise ValueError("athlete.max_hr must be strictly greater than athlete.resting_hr")
        return self
