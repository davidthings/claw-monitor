"""Backdate integration tests — Group 11 (§3.4)."""

import os
import sys
import time
import sqlite3

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_backdate_relative_minutes_db_check(integration_db):
    """Insert a tag with relative backdate and verify DB timestamp."""
    conn = sqlite3.connect(integration_db)
    now = int(time.time())
    ts_backdated = now - 600  # 10 minutes ago

    conn.execute(
        "INSERT INTO tags (ts, recorded_at, category, text, source) VALUES (?, ?, 'coding', 'backdate -10m', 'user')",
        (ts_backdated, now),
    )
    conn.commit()

    row = conn.execute("SELECT ts, recorded_at FROM tags WHERE text = 'backdate -10m'").fetchone()
    assert row is not None
    assert row[0] == ts_backdated
    assert row[1] == now
    assert row[0] < row[1]  # ts should be before recorded_at
    conn.close()


def test_backdate_natural_language_db_check(integration_db):
    """Verify natural language backdate results in correct DB state."""
    conn = sqlite3.connect(integration_db)
    now = int(time.time())
    # "30 minutes ago" = now - 1800
    ts_backdated = now - 1800

    conn.execute(
        "INSERT INTO tags (ts, recorded_at, category, text, source) VALUES (?, ?, 'research', 'backdate natural', 'user')",
        (ts_backdated, now),
    )
    conn.commit()

    row = conn.execute("SELECT ts, recorded_at FROM tags WHERE text = 'backdate natural'").fetchone()
    assert row is not None
    assert row[0] == ts_backdated
    assert row[1] > row[0]
    conn.close()


def test_backdate_iso_db_check(integration_db):
    """Verify ISO-8601 backdate results in correct DB state."""
    conn = sqlite3.connect(integration_db)
    now = int(time.time())
    # A fixed ISO date
    iso_ts = 1741200000  # Some fixed timestamp

    conn.execute(
        "INSERT INTO tags (ts, recorded_at, category, text, source) VALUES (?, ?, 'coding', 'backdate iso', 'user')",
        (iso_ts, now),
    )
    conn.commit()

    row = conn.execute("SELECT ts, recorded_at FROM tags WHERE text = 'backdate iso'").fetchone()
    assert row is not None
    assert row[0] == iso_ts
    assert row[1] == now
    conn.close()
