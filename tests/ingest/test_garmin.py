"""Tests for the GarminClient SDK wrapper."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from health.ingest.garmin import DayBundle, GarminClient

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "garmin"


def _load(name: str) -> dict[str, Any]:
    with (FIXTURE_DIR / name).open() as fh:
        loaded: dict[str, Any] = json.load(fh)
        return loaded


@pytest.fixture
def summary_fixture() -> dict[str, Any]:
    return _load("summary_day.json")


@pytest.fixture
def sleep_fixture() -> dict[str, Any]:
    return _load("sleep_day.json")


def _make_sdk(
    summary: Any = None,
    sleep: Any = None,
    hrv: Any = None,
    body: Any = None,
    activities: Any = None,
    *,
    raise_on: str | None = None,
) -> MagicMock:
    sdk = MagicMock()

    def _maybe(name: str, value: Any) -> Any:
        def call(*_a: Any, **_k: Any) -> Any:
            if raise_on == name:
                raise RuntimeError(f"boom: {name}")
            return value

        return call

    sdk.get_user_summary.side_effect = _maybe("summary", summary)
    sdk.get_sleep_data.side_effect = _maybe("sleep", sleep)
    sdk.get_hrv_data.side_effect = _maybe("hrv", hrv)
    sdk.get_body_composition.side_effect = _maybe("body", body)
    sdk.get_activities_by_date.side_effect = _maybe("activities", activities or [])
    return sdk


def test_fetch_day_populates_all_fields(
    tmp_path: Path,
    summary_fixture: dict[str, Any],
    sleep_fixture: dict[str, Any],
) -> None:
    client = GarminClient("e@x", "pw", tmp_path / "tokens")
    client._api = _make_sdk(
        summary=summary_fixture,
        sleep=sleep_fixture,
        hrv={"hrvSummary": {"calendarDate": "2026-05-10"}},
        body={"weight": 70000},
    )
    bundle = client.fetch_day(date(2026, 5, 10))
    assert isinstance(bundle, DayBundle)
    assert bundle.summary == summary_fixture
    assert bundle.sleep == sleep_fixture
    assert bundle.hrv == {"hrvSummary": {"calendarDate": "2026-05-10"}}
    assert bundle.body_composition == {"weight": 70000}


def test_fetch_day_tolerates_partial_failure(
    tmp_path: Path,
    summary_fixture: dict[str, Any],
) -> None:
    client = GarminClient("e@x", "pw", tmp_path / "tokens")
    client._api = _make_sdk(summary=summary_fixture, raise_on="sleep")
    bundle = client.fetch_day(date(2026, 5, 10))
    assert bundle.summary == summary_fixture
    assert bundle.sleep is None


def test_fetch_activities_success(tmp_path: Path) -> None:
    client = GarminClient("e@x", "pw", tmp_path / "tokens")
    payload = [{"activityId": 1}, {"activityId": 2}]
    client._api = _make_sdk(activities=payload)
    assert client.fetch_activities(date(2026, 5, 1), date(2026, 5, 7)) == payload


def test_fetch_activities_error_returns_empty(tmp_path: Path) -> None:
    client = GarminClient("e@x", "pw", tmp_path / "tokens")
    client._api = _make_sdk(raise_on="activities")
    assert client.fetch_activities(date(2026, 5, 1), date(2026, 5, 7)) == []


def test_login_uses_cached_tokens_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When token_dir has valid cached tokens, no credential login is attempted."""
    cred_login_calls = 0

    class FakeGarmin:
        def __init__(self, email: str | None = None, password: str | None = None) -> None:
            self.email = email
            self.password = password
            self.garth = MagicMock()

        def login(self, token_dir: str | None = None) -> None:
            nonlocal cred_login_calls
            if token_dir is None:
                # credential-based login path
                cred_login_calls += 1

    monkeypatch.setattr("health.ingest.garmin.Garmin", FakeGarmin)
    token_dir = tmp_path / "tokens"
    client = GarminClient("e@x", "pw", token_dir)
    client.login()
    assert cred_login_calls == 0
    assert token_dir.exists()


def test_login_falls_back_to_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cred_login_calls = 0
    dump_calls: list[str] = []

    class FakeGarth:
        def dump(self, path: str) -> None:
            dump_calls.append(path)

    class FakeGarmin:
        def __init__(self, email: str | None = None, password: str | None = None) -> None:
            self.email = email
            self.password = password
            self.garth = FakeGarth()

        def login(self, token_dir: str | None = None) -> None:
            nonlocal cred_login_calls
            if token_dir is not None:
                raise FileNotFoundError("no cached tokens")
            cred_login_calls += 1

    monkeypatch.setattr("health.ingest.garmin.Garmin", FakeGarmin)
    client = GarminClient("e@x", "pw", tmp_path / "tokens")
    client.login()
    assert cred_login_calls == 1
    assert len(dump_calls) == 1


def test_login_raises_on_rate_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Credential login that 429s must raise GarminLoginError, not AttributeError."""
    from health.ingest.garmin import GarminLoginError

    class FakeGarmin:
        def __init__(self, email: str | None = None, password: str | None = None) -> None:
            pass

        def login(self, token_dir: str | None = None) -> None:
            if token_dir is not None:
                raise FileNotFoundError("no cached tokens")
            raise RuntimeError("Mobile login returned 429 — IP rate limited by Garmin")

    monkeypatch.setattr("health.ingest.garmin.Garmin", FakeGarmin)
    client = GarminClient("e@x", "pw", tmp_path / "tokens")
    with pytest.raises(GarminLoginError, match="rate-limited"):
        client.login()


def test_login_raises_when_garth_missing_after_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If SDK swallows a 429 internally, .garth is never attached — fail loudly."""
    from health.ingest.garmin import GarminLoginError

    class FakeGarmin:
        def __init__(self, email: str | None = None, password: str | None = None) -> None:
            pass

        def login(self, token_dir: str | None = None) -> None:
            if token_dir is not None:
                raise FileNotFoundError("no cached tokens")
            # Successful return but no .garth attached — mimic SDK swallowing the 429.

    monkeypatch.setattr("health.ingest.garmin.Garmin", FakeGarmin)
    client = GarminClient("e@x", "pw", tmp_path / "tokens")
    with pytest.raises(GarminLoginError, match="rate limiting"):
        client.login()
