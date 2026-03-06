"""Shared fixtures for claw-proxy tests."""

import sys
import os

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestServer, TestClient

# Allow imports from claw-proxy/ and tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from helpers import (
    ANTHROPIC_SSE, ANTHROPIC_ERROR_SSE, OPENAI_SSE, OPENAI_NO_USAGE_SSE,
    make_upstream_app, make_error_app, make_token_receiver_app,
    make_slow_token_receiver_app, get_proxy_class, get_sse_body,
    create_proxy_app,
)


# ---------------------------------------------------------------------------
# Provider-parametrized fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(params=["anthropic", "openai", "llama"])
def provider(request):
    return request.param


@pytest_asyncio.fixture
async def mock_upstream(provider):
    sse = get_sse_body(provider)
    app = make_upstream_app(sse, provider)
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest_asyncio.fixture
async def mock_upstream_error_500():
    app = make_error_app(500)
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest_asyncio.fixture
async def mock_token_receiver():
    app = make_token_receiver_app()
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest_asyncio.fixture
async def slow_token_receiver():
    app = make_slow_token_receiver_app()
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest_asyncio.fixture
async def proxy_client(provider, mock_upstream, mock_token_receiver):
    cls = get_proxy_class(provider)
    upstream_url = str(mock_upstream.make_url(""))
    cm_port = mock_token_receiver.port
    app = await create_proxy_app(cls, upstream_url, cm_port)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()
    await server.close()


# ---------------------------------------------------------------------------
# Anthropic-specific fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def anthropic_upstream():
    app = make_upstream_app(ANTHROPIC_SSE, "anthropic")
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest_asyncio.fixture
async def anthropic_error_upstream():
    app = make_upstream_app(ANTHROPIC_ERROR_SSE, "anthropic")
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest_asyncio.fixture
async def anthropic_proxy(anthropic_upstream, mock_token_receiver):
    from proxy_anthropic import AnthropicProxy
    upstream_url = str(anthropic_upstream.make_url(""))
    cm_port = mock_token_receiver.port
    app = await create_proxy_app(AnthropicProxy, upstream_url, cm_port)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()
    await server.close()


@pytest_asyncio.fixture
async def anthropic_error_proxy(anthropic_error_upstream, mock_token_receiver):
    from proxy_anthropic import AnthropicProxy
    upstream_url = str(anthropic_error_upstream.make_url(""))
    cm_port = mock_token_receiver.port
    app = await create_proxy_app(AnthropicProxy, upstream_url, cm_port)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()
    await server.close()


# ---------------------------------------------------------------------------
# OpenAI-specific fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def openai_upstream():
    app = make_upstream_app(OPENAI_SSE, "openai")
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest_asyncio.fixture
async def openai_no_usage_upstream():
    app = make_upstream_app(OPENAI_NO_USAGE_SSE, "openai")
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest_asyncio.fixture
async def openai_proxy(openai_upstream, mock_token_receiver):
    from proxy_openai import OpenAIProxy
    upstream_url = str(openai_upstream.make_url(""))
    cm_port = mock_token_receiver.port
    app = await create_proxy_app(OpenAIProxy, upstream_url, cm_port)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()
    await server.close()


@pytest_asyncio.fixture
async def openai_no_usage_proxy(openai_no_usage_upstream, mock_token_receiver):
    from proxy_openai import OpenAIProxy
    upstream_url = str(openai_no_usage_upstream.make_url(""))
    cm_port = mock_token_receiver.port
    app = await create_proxy_app(OpenAIProxy, upstream_url, cm_port)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()
    await server.close()


# ---------------------------------------------------------------------------
# Llama-specific fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def llama_upstream():
    app = make_upstream_app(OPENAI_SSE, "llama")
    server = TestServer(app)
    await server.start_server()
    yield server
    await server.close()


@pytest_asyncio.fixture
async def llama_proxy(llama_upstream, mock_token_receiver):
    from proxy_llama import LlamaProxy
    upstream_url = str(llama_upstream.make_url(""))
    cm_port = mock_token_receiver.port
    app = await create_proxy_app(LlamaProxy, upstream_url, cm_port)
    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()
    await server.close()
