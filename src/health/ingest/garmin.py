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
    GarminConnectTooManyRequestsError,
    HTTPError,
)

log = logging.getLogger(__name__)


class GarminLoginError(RuntimeError):
    """Raised when both cached-token resume and credential login fail."""


# Exceptions that mean "cached tokens are gone or stale — fall back to creds".
_RESUME_EXC: tuple[type[BaseException], ...] = (
    FileNotFoundError,
    HTTPError,
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
        """Resume from cached tokens if present, otherwise log in with creds.

        Cached-token resume failures fall through to credential login. If
        credential login also fails (e.g. Garmin returning HTTP 429), raise
        ``GarminLoginError`` so the caller can show a clean message instead
        of a deep SDK stack trace.
        """
        self._token_dir.mkdir(parents=True, exist_ok=True)
        try:
            api = Garmin()
            api.login(tokenstore=str(self._token_dir))
        except _RESUME_EXC as resume_exc:
            log.info("cached tokens unavailable (%s); logging in with credentials", resume_exc)
            api = Garmin(email=self._email, password=self._password)
            try:
                api.login()
            except GarminConnectTooManyRequestsError as exc:
                raise GarminLoginError(_explain_rate_limit()) from exc
            except Exception as exc:
                raise GarminLoginError(_explain_login_error(exc)) from exc
            # The SDK attaches its session as ``.client`` after a successful
            # login; if it's missing or not authenticated the login failed
            # silently (e.g. the SDK swallowed a 429) and we must not pretend
            # we're authenticated.
            client = getattr(api, "client", None)
            if client is None or not getattr(client, "is_authenticated", False):
                raise GarminLoginError(_explain_rate_limit()) from None
            client.dump(str(self._token_dir))
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


def _explain_rate_limit() -> str:
    return (
        "Garmin rate-limited this IP (HTTP 429). "
        "Wait 15-60 minutes, then retry. Repeated failures may require "
        "logging in via the Garmin Connect app or website first."
    )


def _explain_login_error(exc: BaseException) -> str:
    """Produce a one-line, human-readable login-error message."""
    msg = str(exc) or exc.__class__.__name__
    if "429" in msg or "rate" in msg.lower():
        return _explain_rate_limit()
    return f"Garmin login failed: {msg}"


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
