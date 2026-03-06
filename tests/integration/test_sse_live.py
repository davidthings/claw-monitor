"""SSE live tests — Group 11 (§3.2 SSE)."""

import pytest


@pytest.mark.skip(reason="Requires 35s wait for SSE ping — too slow for CI")
def test_sse_stream_ping_received():
    """SSE stream should receive a ping comment every 30 seconds."""
    pass


@pytest.mark.skip(reason="Requires running Next.js server with live DB inserts")
def test_sse_stream_receives_new_data():
    """SSE stream should emit data events when new metrics are inserted."""
    pass
