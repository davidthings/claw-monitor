"""Group F: Operational — parametrized over all 3 proxies."""

import json

import pytest
import pytest_asyncio
from aiohttp.test_utils import TestServer, TestClient

from helpers import get_proxy_class

pytestmark = pytest.mark.asyncio


async def test_health_endpoint(proxy_client, provider):
    """GET /health returns {"ok": true}."""
    resp = await proxy_client.get("/health")
    assert resp.status == 200
    data = await resp.json()
    assert data == {"ok": True}


async def test_proxy_respects_port_env(provider, monkeypatch):
    """Proxy reads port from env var."""
    env_map = {
        "anthropic": "CM_PROXY_ANTHROPIC_PORT",
        "openai": "CM_PROXY_OPENAI_PORT",
        "llama": "CM_PROXY_LLAMA_PORT",
    }
    monkeypatch.setenv(env_map[provider], "15555")
    cls = get_proxy_class(provider)
    proxy = cls()
    assert proxy.proxy_port == 15555


async def test_proxy_respects_upstream_url_env(provider, monkeypatch):
    """Upstream URL override via env var works."""
    env_map = {
        "anthropic": ("ANTHROPIC_BASE_URL", "http://custom:9000"),
        "openai": ("OPENAI_BASE_URL", "http://custom:9001"),
        "llama": ("LLAMA_BASE_URL", "http://custom:9002"),
    }
    env_var, url = env_map[provider]
    monkeypatch.setenv(env_var, url)
    cls = get_proxy_class(provider)
    proxy = cls()
    assert proxy.upstream_url == url
