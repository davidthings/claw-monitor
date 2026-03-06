"""Group A: Forwarding correctness — parametrized over all 3 proxies."""

import asyncio
import json

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient

from helpers import (
    get_proxy_class, get_sse_body, make_upstream_app,
    make_error_app, make_token_receiver_app, create_proxy_app,
)

pytestmark = pytest.mark.asyncio


async def test_proxy_forwards_post_body(proxy_client, mock_upstream, provider):
    """Request body reaches upstream unchanged."""
    body = {"model": "test-model", "messages": [{"role": "user", "content": "hi"}]}
    await proxy_client.post("/v1/messages", json=body)
    received = mock_upstream.app["received_requests"]
    assert len(received) >= 1
    assert json.loads(received[0]["body"]) == body


async def test_proxy_forwards_auth_headers(proxy_client, mock_upstream, provider):
    """Authorization header passed through."""
    body = {"model": "test-model"}
    await proxy_client.post(
        "/v1/messages",
        json=body,
        headers={"Authorization": "Bearer sk-test-key-123"},
    )
    received = mock_upstream.app["received_requests"]
    assert received[0]["headers"].get("Authorization") == "Bearer sk-test-key-123"


async def test_proxy_returns_non_streaming_response(proxy_client, provider):
    """Non-streaming JSON response returned correctly."""
    body = {"model": "test-model", "stream": False}
    resp = await proxy_client.post("/v1/messages", json=body)
    assert resp.status == 200
    data = await resp.json()
    assert data["result"] == "ok"


async def test_proxy_streams_response_in_realtime(proxy_client, provider):
    """SSE chunks arrive at client as upstream emits them."""
    body = {"model": "test-model", "stream": True}
    resp = await proxy_client.post("/v1/messages", json=body)
    assert resp.status == 200
    assert "text/event-stream" in resp.headers.get("Content-Type", "")
    text = await resp.text()
    assert "data:" in text


async def test_proxy_preserves_status_codes(provider, mock_token_receiver):
    """400/429/500 from upstream returned to client unchanged."""
    for status in [400, 429, 500]:
        error_app = make_error_app(status)
        error_server = TestServer(error_app)
        await error_server.start_server()
        try:
            cls = get_proxy_class(provider)
            upstream_url = str(error_server.make_url(""))
            cm_port = mock_token_receiver.port
            app = await create_proxy_app(cls, upstream_url, cm_port)
            proxy_server = TestServer(app)
            await proxy_server.start_server()
            client = TestClient(proxy_server)
            await client.start_server()
            try:
                resp = await client.post("/v1/messages", json={"model": "m"})
                assert resp.status == status, f"Expected {status}, got {resp.status}"
            finally:
                await client.close()
                await proxy_server.close()
        finally:
            await error_server.close()
