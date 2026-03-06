"""Group E: Fail-open behaviour — parametrized over all 3 proxies."""

import asyncio

import pytest
from aiohttp.test_utils import TestServer, TestClient

from helpers import (
    get_proxy_class, get_sse_body, make_upstream_app, create_proxy_app,
)

pytestmark = pytest.mark.asyncio


async def test_upstream_down_returns_503(provider, mock_token_receiver):
    """Upstream unreachable -> 503, no hang."""
    cls = get_proxy_class(provider)
    app = await create_proxy_app(cls, "http://127.0.0.1:19999", mock_token_receiver.port)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.post("/v1/messages", json={"model": "m"})
        assert resp.status == 503
    finally:
        await client.close()
        await server.close()


async def test_upstream_500_returned_to_client(proxy_client, mock_upstream_error_500, provider, mock_token_receiver):
    """500 from upstream flows through — using dedicated error upstream."""
    cls = get_proxy_class(provider)
    upstream_url = str(mock_upstream_error_500.make_url(""))
    cm_port = mock_token_receiver.port
    app = await create_proxy_app(cls, upstream_url, cm_port)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.post("/v1/messages", json={"model": "m"})
        assert resp.status == 500
    finally:
        await client.close()
        await server.close()


async def test_token_reporter_down_does_not_block(provider, mock_upstream):
    """Token receiver down -> proxy still completes API call."""
    cls = get_proxy_class(provider)
    upstream_url = str(mock_upstream.make_url(""))
    app = await create_proxy_app(cls, upstream_url, 19998)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    try:
        body = {"model": "test", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
        resp = await client.post("/v1/messages", json=body)
        assert resp.status == 200
        await resp.read()
    finally:
        await client.close()
        await server.close()


async def test_token_reporter_timeout_does_not_block(provider, mock_upstream, slow_token_receiver):
    """Slow token reporter (>2s) -> proxy still completes quickly."""
    cls = get_proxy_class(provider)
    upstream_url = str(mock_upstream.make_url(""))
    cm_port = slow_token_receiver.port
    app = await create_proxy_app(cls, upstream_url, cm_port)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    try:
        body = {"model": "test", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
        resp = await client.post("/v1/messages", json=body)
        assert resp.status == 200
        await resp.read()
    finally:
        await client.close()
        await server.close()


async def test_concurrent_streams_do_not_mix_tokens(provider, mock_token_receiver):
    """Two simultaneous requests accumulate tokens independently."""
    cls = get_proxy_class(provider)
    sse = get_sse_body(provider)
    upstream_app = make_upstream_app(sse, provider)
    upstream_server = TestServer(upstream_app)
    await upstream_server.start_server()
    try:
        upstream_url = str(upstream_server.make_url(""))
        cm_port = mock_token_receiver.port
        app = await create_proxy_app(cls, upstream_url, cm_port)
        server = TestServer(app)
        await server.start_server()
        client = TestClient(server)
        await client.start_server()
        try:
            body = {"model": "test", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
            resp1, resp2 = await asyncio.gather(
                client.post("/v1/messages", json=body),
                client.post("/v1/messages", json=body),
            )
            await resp1.read()
            await resp2.read()
            await asyncio.sleep(0.5)
            calls = mock_token_receiver.app["calls"]
            assert len(calls) == 2
            for call in calls:
                assert call["tokens_in"] > 0
                assert call["tokens_out"] > 0
        finally:
            await client.close()
            await server.close()
    finally:
        await upstream_server.close()
