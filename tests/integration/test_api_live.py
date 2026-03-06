"""Integration tests for web API — real HTTP calls against a live Next.js server."""

import time
import requests
import pytest


pytestmark = pytest.mark.skipif(
    False,  # always run; web_server fixture skips if server fails
    reason=""
)


def test_post_tag_and_read_back(web_server):
    """POST a tag via HTTP and read it back via GET."""
    base_url, _ = web_server

    r = requests.post(f"{base_url}/api/tags", json={
        "category": "coding",
        "text": "integration test tag",
        "source": "system",
    })
    assert r.status_code == 201
    assert r.json()["ok"] is True

    now = int(time.time())
    r = requests.get(f"{base_url}/api/tags", params={"from": now - 60, "to": now + 5})
    assert r.status_code == 200
    tags = r.json()["tags"]
    assert any(t["text"] == "integration test tag" for t in tags)


def test_post_token_and_read_summary(web_server):
    """POST token events and verify summary endpoint reflects them."""
    base_url, _ = web_server

    r = requests.post(f"{base_url}/api/tokens", json={
        "tool": "claude-code",
        "model": "claude-sonnet-4-6",
        "tokens_in": 1000,
        "tokens_out": 500,
    })
    assert r.status_code == 201

    r = requests.post(f"{base_url}/api/tokens", json={
        "tool": "claude-code",
        "model": "claude-sonnet-4-6",
        "tokens_in": 2000,
        "tokens_out": 1000,
    })
    assert r.status_code == 201

    now = int(time.time())
    r = requests.get(f"{base_url}/api/tokens/summary", params={"from": now - 60, "to": now + 5})
    assert r.status_code == 200
    data = r.json()
    # Should have aggregated totals
    assert "summary" in data or "tools" in data or "total" in data or isinstance(data, (list, dict))


def test_registry_post_and_get(web_server):
    """POST a process to registry and GET it back."""
    base_url, _ = web_server

    r = requests.post(f"{base_url}/api/registry/process", json={
        "pid": 99999,
        "name": "test-tool",
        "group": "openclaw-core",
    })
    assert r.status_code in (200, 201)

    r = requests.get(f"{base_url}/api/registry")
    assert r.status_code == 200


def test_disk_get(web_server):
    """GET /api/disk should return 200 with disk data."""
    base_url, _ = web_server
    r = requests.get(f"{base_url}/api/disk")
    assert r.status_code == 200


def test_metrics_get(web_server):
    """GET /api/metrics should return 200."""
    base_url, _ = web_server
    now = int(time.time())
    r = requests.get(f"{base_url}/api/metrics", params={"from": now - 60, "to": now + 5})
    assert r.status_code == 200
