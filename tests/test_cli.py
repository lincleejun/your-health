"""Tests for the ``health`` CLI."""

from __future__ import annotations

import sys
import types
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import ClassVar

import pytest
from typer.testing import CliRunner

from health.cli import app


@dataclass
class _FakeSummary:
    run_id: int = 42
    days_requested: int = 3
    rows_written: int = 17
    errors: list[str] = field(default_factory=list)
    started_at: datetime = datetime(2025, 1, 1, 8, 0, 0)
    finished_at: datetime = datetime(2025, 1, 1, 8, 0, 5)


class _FakeClient:
    """Stand-in for GarminClient — login is a no-op."""

    last_init: ClassVar[dict[str, object]] = {}

    def __init__(self, email: str, password: str, token_dir: Path) -> None:
        type(self).last_init = {"email": email, "password": password, "token_dir": token_dir}

    def login(self) -> None:
        return None


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def tmp_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "data" / "health.db", tmp_path / "tokens"


@pytest.fixture
def patch_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_FakeClient]]:
    monkeypatch.setattr("health.cli.GarminClient", _FakeClient)
    yield _FakeClient


@pytest.fixture
def patch_runner(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, object]]:
    """Install a fake ``health.ingest.runner`` module with a recording ``ingest_range``."""
    captured: dict[str, object] = {}

    def fake_ingest_range(conn: object, client: object, start: date, end: date) -> _FakeSummary:
        captured["conn"] = conn
        captured["client"] = client
        captured["start"] = start
        captured["end"] = end
        return _FakeSummary(
            days_requested=(end - start).days + 1,
            started_at=datetime.combine(start, datetime.min.time()),
            finished_at=datetime.combine(end, datetime.min.time()),
        )

    mod = types.ModuleType("health.ingest.runner")
    mod.ingest_range = fake_ingest_range  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "health.ingest.runner", mod)
    yield captured


def test_missing_credentials_exits_one(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GARMIN_EMAIL", raising=False)
    monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)  # ensure no stray .env nearby

    result = runner.invoke(app, ["ingest", "--days", "1"])
    assert result.exit_code == 1
    assert "GARMIN_EMAIL" in result.stderr


def test_happy_path_renders_summary(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_paths: tuple[Path, Path],
    patch_client: type[_FakeClient],
    patch_runner: dict[str, object],
) -> None:
    db_path, token_dir = tmp_paths
    monkeypatch.setenv("GARMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("GARMIN_PASSWORD", "pw")

    result = runner.invoke(
        app,
        [
            "ingest",
            "--days",
            "3",
            "--start",
            "2025-01-01",
            "--db",
            str(db_path),
            "--token-dir",
            str(token_dir),
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert "42" in result.stdout  # run_id
    assert "17" in result.stdout  # rows_written

    # Verify date range was resolved correctly.
    assert patch_runner["start"] == date(2025, 1, 1)
    assert patch_runner["end"] == date(2025, 1, 3)

    # DB file was created.
    assert db_path.is_file()

    # Client was constructed with expected token_dir.
    assert _FakeClient.last_init["token_dir"] == token_dir


def test_db_created_when_missing(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    tmp_paths: tuple[Path, Path],
    patch_client: type[_FakeClient],
    patch_runner: dict[str, object],
) -> None:
    db_path, token_dir = tmp_paths
    assert not db_path.exists()
    assert not db_path.parent.exists()

    monkeypatch.setenv("GARMIN_EMAIL", "a@b.c")
    monkeypatch.setenv("GARMIN_PASSWORD", "pw")

    result = runner.invoke(
        app,
        [
            "ingest",
            "--days",
            "1",
            "--start",
            "2025-02-01",
            "--db",
            str(db_path),
            "--token-dir",
            str(token_dir),
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert db_path.is_file()
    assert db_path.parent.is_dir()
