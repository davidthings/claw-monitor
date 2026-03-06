"""SSE live tests — real HTTP streaming against test server."""

import pytest
import requests


def test_sse_stream_connects(web_server):
    """SSE /api/metrics/stream should respond 200 with text/event-stream and send initial comment."""
    base_url, _ = web_server

    # The SSE endpoint sends ': connected\n\n' immediately on open,
    # which causes HTTP headers to be flushed right away.
    r = requests.get(f"{base_url}/api/metrics/stream", stream=True, timeout=(5, 5))
    try:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("Content-Type", "")

        # Read the initial ': connected' comment from the stream
        for line in r.iter_lines(chunk_size=1):
            if line:
                assert line.startswith(b":"), f"Expected SSE comment, got: {line}"
                break
    finally:
        r.close()


@pytest.mark.skip(reason="Requires 35s wait for SSE ping — too slow for CI")
def test_sse_stream_ping_received(web_server):
    """SSE stream should receive a ping comment every 30 seconds."""
    pass


@pytest.mark.skip(reason="Requires running Next.js server with live DB inserts")
def test_sse_stream_receives_new_data(web_server):
    """SSE stream should emit data events when new metrics are inserted."""
    pass
