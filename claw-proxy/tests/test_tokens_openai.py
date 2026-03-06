"""Group C: Token extraction — OpenAI."""

import asyncio
import json

import pytest

pytestmark = pytest.mark.asyncio


async def test_openai_extracts_tokens_from_final_usage_chunk(
    openai_proxy, mock_token_receiver
):
    body = {"model": "gpt-4o-mini", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await openai_proxy.post("/v1/chat/completions", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert len(calls) >= 1
    assert calls[0]["tokens_in"] == 150
    assert calls[0]["tokens_out"] == 5


async def test_openai_posts_token_event_after_done(
    openai_proxy, mock_token_receiver
):
    body = {"model": "gpt-4o-mini", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await openai_proxy.post("/v1/chat/completions", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert len(calls) == 1
    assert calls[0]["tool"] == "openclaw-openai"


async def test_openai_token_event_has_correct_model(
    openai_proxy, mock_token_receiver
):
    body = {"model": "gpt-4o-mini", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await openai_proxy.post("/v1/chat/completions", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert calls[0]["model"] == "gpt-4o-mini"


async def test_openai_no_token_post_if_no_usage_field(
    openai_no_usage_proxy, mock_token_receiver
):
    body = {"model": "gpt-4o-mini", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await openai_no_usage_proxy.post("/v1/chat/completions", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert len(calls) == 0
