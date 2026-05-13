"""Thin, typed wrapper around the ``garminconnect`` SDK.

Adds two affordances over the raw SDK:

* OAuth token persistence — we cache Garth tokens under a directory so we don't
  prompt for credentials on every run.
* Per-field exception tolerance on the day bundle — one missing Garmin response
  must not abort the day's ingest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
)

try:  # garth is a transitive dep of garminconnect
    from garth.exc import GarthHTTPError
except ImportError:  # pragma: no cover - safety net for older garth releases
    # reason: garth<0.4 didn't expose this class; alias to a generic exception
    GarthHTTPError = Exception

log = logging.getLogger(__name__)

_LOGIN_EXC: tuple[type[BaseException], ...] = (
    FileNotFoundError,
    GarthHTTPError,
    GarminConnectAuthenticationError,
)


@dataclass
class DayBundle:
    """A day's worth of raw Garmin payloads. Any field may be ``None``."""

    date: date
    summary: dict[str, Any] | None = None
    sleep: dict[str, Any] | None = None
    hrv: dict[str, Any] | None = None
    body_composition: dict[str, Any] | None = None


class GarminClient:
    """Authenticated Garmin Connect client with token persistence."""

    def __init__(self, email: str, password: str, token_dir: Path) -> None:
        self._email = email
        self._password = password
        self._token_dir = token_dir
        self._api: Any | None = None

    def login(self) -> None:
        """Resume from cached tokens if present, otherwise log in with creds."""
        self._token_dir.mkdir(parents=True, exist_ok=True)
        try:
            api = Garmin()
            api.login(str(self._token_dir))
        except _LOGIN_EXC as exc:
            log.info("cached tokens unavailable (%s); logging in with credentials", exc)
            api = Garmin(email=self._email, password=self._password)
            api.login()
            api.garth.dump(str(self._token_dir))
        self._api = api

    def _require_api(self) -> Any:
        if self._api is None:
            raise RuntimeError("GarminClient.login() must be called before fetching")
        return self._api

    def fetch_day(self, d: date) -> DayBundle:
        """Fetch the day-scoped payloads. Per-call failures degrade to ``None``."""
        api = self._require_api()
        iso = d.isoformat()
        return DayBundle(
            date=d,
            summary=_safe_call(api.get_user_summary, iso, label="summary"),
            sleep=_safe_call(api.get_sleep_data, iso, label="sleep"),
            hrv=_safe_call(api.get_hrv_data, iso, label="hrv"),
            body_composition=_safe_call(
                api.get_body_composition, iso, iso, label="body_composition"
            ),
        )

    def fetch_activities(self, start: date, end: date) -> list[dict[str, Any]]:
        """Return activity dicts in ``[start, end]``. On error, return ``[]``."""
        api = self._require_api()
        try:
            result = api.get_activities_by_date(start.isoformat(), end.isoformat())
        except Exception:
            log.warning("get_activities_by_date failed for %s..%s", start, end, exc_info=True)
            return []
        if not isinstance(result, list):
            log.warning("unexpected activities payload type: %s", type(result).__name__)
            return []
        return list(result)


def _safe_call(fn: Any, *args: Any, label: str) -> dict[str, Any] | None:
    """Invoke a SDK call; on failure, warn and return None."""
    try:
        result = fn(*args)
    except Exception:
        log.warning("garmin %s call failed", label, exc_info=True)
        return None
    if result is None:
        return None
    if not isinstance(result, dict):
        log.warning("garmin %s returned non-dict: %s", label, type(result).__name__)
        return None
    return result
