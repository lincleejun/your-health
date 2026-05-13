"""YAML loader for ``plan.yaml`` with friendly error wrapping."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from health.plan.schema import Plan


class PlanLoadError(Exception):
    """Raised when the plan file is missing, unreadable, or invalid YAML/schema."""


def load_plan(path: Path) -> Plan:
    """Read a YAML file and return a validated :class:`Plan`.

    - ``FileNotFoundError`` → :class:`PlanLoadError` with a friendly message.
    - YAML parse errors → :class:`PlanLoadError` wrapping the underlying error.
    - Pydantic validation errors → :class:`PlanLoadError` listing the first
      three issues.
    """
    try:
        raw = path.read_text()
    except FileNotFoundError as exc:
        raise PlanLoadError(f"plan file not found: {path}") from exc
    except OSError as exc:
        raise PlanLoadError(f"could not read plan file {path}: {exc}") from exc

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise PlanLoadError(f"invalid YAML in {path}: {exc}") from exc

    if data is None:
        raise PlanLoadError(f"plan file {path} is empty")
    if not isinstance(data, dict):
        raise PlanLoadError(f"plan file {path} must be a mapping at the top level")

    try:
        return Plan.model_validate(data)
    except ValidationError as exc:
        issues = exc.errors()[:3]
        formatted = "; ".join(
            f"{'.'.join(str(p) for p in issue['loc']) or '<root>'}: {issue['msg']}"
            for issue in issues
        )
        raise PlanLoadError(f"plan validation failed for {path}: {formatted}") from exc
