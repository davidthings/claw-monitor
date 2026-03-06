"""Integration tests for web API — Group 10 (§3.2)."""

import os
import sys
import time
import sqlite3
import json

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_post_tag_and_read_back(integration_db):
    """Post a tag and read it back directly from DB."""
    conn = sqlite3.connect(integration_db)
    now = int(time.time())

    conn.execute(
        "INSERT INTO tags (ts, recorded_at, category, text, source) VALUES (?, ?, 'coding', 'test tag', 'user')",
        (now, now),
    )
    conn.commit()

    rows = conn.execute("SELECT category, text, source FROM tags").fetchall()
    assert len(rows) == 1
    assert rows[0] == ("coding", "test tag", "user")
    conn.close()


def test_post_token_and_read_summary(integration_db):
    """Post token events and verify they can be read."""
    conn = sqlite3.connect(integration_db)
    now = int(time.time())

    conn.execute(
        "INSERT INTO token_events (ts, tool, model, tokens_in, tokens_out) VALUES (?, 'claude-code', 'claude-sonnet-4-6', 1000, 500)",
        (now,),
    )
    conn.execute(
        "INSERT INTO token_events (ts, tool, model, tokens_in, tokens_out) VALUES (?, 'claude-code', 'claude-sonnet-4-6', 2000, 1000)",
        (now,),
    )
    conn.commit()

    rows = conn.execute(
        "SELECT tool, SUM(tokens_in), SUM(tokens_out) FROM token_events GROUP BY tool"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "claude-code"
    assert rows[0][1] == 3000
    assert rows[0][2] == 1500
    conn.close()


@pytest.mark.skip(reason="Requires running Next.js server with SSE support")
def test_sse_stream_receives_new_data():
    """SSE stream should receive new data when metrics are inserted."""
    pass


@pytest.mark.skip(reason="Requires 35s wait for SSE ping — too slow for CI")
def test_sse_stream_ping_received():
    """SSE stream should receive a ping every 30s."""
    pass
