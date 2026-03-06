"""Group B: Token extraction — Anthropic."""

import asyncio
import json

import pytest

pytestmark = pytest.mark.asyncio


async def test_anthropic_extracts_input_tokens_from_message_start(
    anthropic_proxy, mock_token_receiver
):
    body = {"model": "claude-haiku-4-5", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await anthropic_proxy.post("/v1/messages", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert len(calls) >= 1
    assert calls[0]["tokens_in"] == 150


async def test_anthropic_extracts_output_tokens_from_message_delta(
    anthropic_proxy, mock_token_receiver
):
    body = {"model": "claude-haiku-4-5", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await anthropic_proxy.post("/v1/messages", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert len(calls) >= 1
    assert calls[0]["tokens_out"] == 1


async def test_anthropic_posts_token_event_after_stream_close(
    anthropic_proxy, mock_token_receiver
):
    body = {"model": "claude-haiku-4-5", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await anthropic_proxy.post("/v1/messages", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert len(calls) == 1
    assert "tool" in calls[0]
    assert "model" in calls[0]
    assert "tokens_in" in calls[0]
    assert "tokens_out" in calls[0]


async def test_anthropic_token_event_has_correct_model(
    anthropic_proxy, mock_token_receiver
):
    body = {"model": "claude-haiku-4-5", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await anthropic_proxy.post("/v1/messages", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert calls[0]["model"] == "claude-haiku-4-5"


async def test_anthropic_token_event_session_id_from_header(
    anthropic_proxy, mock_token_receiver
):
    body = {"model": "claude-haiku-4-5", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await anthropic_proxy.post(
        "/v1/messages", json=body,
        headers={"X-Claw-Session": "sess-abc-123"},
    )
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert calls[0]["session_id"] == "sess-abc-123"


async def test_anthropic_no_token_post_on_error_stream(
    anthropic_error_proxy, mock_token_receiver
):
    body = {"model": "claude-haiku-4-5", "stream": True, "messages": [{"role": "user", "content": "hi"}]}
    resp = await anthropic_error_proxy.post("/v1/messages", json=body)
    await resp.read()
    await asyncio.sleep(0.5)
    calls = mock_token_receiver.app["calls"]
    assert len(calls) == 0
