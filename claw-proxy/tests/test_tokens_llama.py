"""Group D: Token extraction — Llama.cpp."""

import asyncio
import json

import pytest

pytestmark = pytest.mark.asyncio


async def test_llama_extracts_tokens_openai_compatible(
    llama_proxy, mock_token_receiver
):
    body = {"model": "qwen3-35b", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await llama_proxy.post("/v1/chat/completions", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert len(calls) >= 1
    assert calls[0]["tokens_in"] == 150
    assert calls[0]["tokens_out"] == 5


async def test_llama_tool_defaults_to_llama_local(
    llama_proxy, mock_token_receiver
):
    body = {"model": "qwen3-35b", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await llama_proxy.post("/v1/chat/completions", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert calls[0]["tool"] == "llama-local"


async def test_llama_upstream_is_local_not_remote():
    from proxy_llama import LlamaProxy
    proxy = LlamaProxy()
    assert "localhost" in proxy.upstream_url or "127.0.0.1" in proxy.upstream_url
