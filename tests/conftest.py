"""Shared pytest fixtures for the health test suite."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest


@pytest.fixture
def db_conn() -> Iterator[sqlite3.Connection]:
    """In-memory SQLite connection with foreign keys on and Row factory.

    Each test gets a fresh, isolated database; the connection is closed
    on teardown.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()
