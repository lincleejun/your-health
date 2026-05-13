"""SQLite connection helpers for the health database."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys on and Row factory set.

    Creates the parent directory if missing so callers can pass a fresh path.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    """Apply schema.sql. Idempotent — safe to call on an already-initialised DB."""
    sql = SCHEMA_PATH.read_text()
    conn.executescript(sql)


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Context manager that commits on success and rolls back on exception."""
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
