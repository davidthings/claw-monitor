"""Shared helpers for claw-proxy tests."""

import asyncio
import json
import sys
import os

from aiohttp import web

# Allow imports from claw-proxy/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# SSE response data
# ---------------------------------------------------------------------------

ANTHROPIC_SSE = """\
event: message_start
data: {"type":"message_start","message":{"model":"claude-haiku-4-5","usage":{"input_tokens":150}}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: message_delta
data: {"type":"message_delta","usage":{"output_tokens":1}}

event: message_stop
data: {"type":"message_stop"}

"""

OPENAI_SSE = """\
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":150,"completion_tokens":5,"total_tokens":155}}

data: [DONE]

"""

ANTHROPIC_ERROR_SSE = """\
event: error
data: {"type":"error","error":{"type":"overloaded_error","message":"Overloaded"}}

"""

OPENAI_NO_USAGE_SSE = """\
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]

"""


# ---------------------------------------------------------------------------
# Mock server factories
# ---------------------------------------------------------------------------

def make_upstream_app(sse_body, provider):
    """Create a mock upstream that records requests and returns SSE or JSON."""
    app = web.Application()
    app["received_requests"] = []

    async def handle(request):
        body = await request.read()
        app["received_requests"].append({
            "method": request.method,
            "path": request.path,
            "headers": dict(request.headers),
            "body": body,
        })
        try:
            data = json.loads(body)
            stream = data.get("stream", False)
        except Exception:
            stream = False

        if stream:
            resp = web.StreamResponse(
                status=200,
                headers={"Content-Type": "text/event-stream"},
            )
            await resp.prepare(request)
            for line in sse_body.split("\n"):
                await resp.write((line + "\n").encode())
                await asyncio.sleep(0.01)
            await resp.write_eof()
            return resp
        else:
            return web.json_response({"result": "ok", "model": "test-model"})

    app.router.add_route("*", "/{path_info:.*}", handle)
    return app


def make_error_app(status_code):
    """Create upstream that always returns an error status."""
    app = web.Application()

    async def handle(request):
        await request.read()
        return web.Response(status=status_code, text=f"Error {status_code}")

    app.router.add_route("*", "/{path_info:.*}", handle)
    return app


def make_token_receiver_app():
    app = web.Application()
    app["calls"] = []

    async def handle(request):
        body = await request.json()
        app["calls"].append(body)
        return web.json_response({"ok": True})

    app.router.add_post("/api/tokens", handle)
    return app


def make_slow_token_receiver_app():
    app = web.Application()
    app["calls"] = []

    async def handle(request):
        body = await request.json()
        app["calls"].append(body)
        await asyncio.sleep(10)
        return web.json_response({"ok": True})

    app.router.add_post("/api/tokens", handle)
    return app


# ---------------------------------------------------------------------------
# Proxy helpers
# ---------------------------------------------------------------------------

def get_proxy_class(provider_name):
    if provider_name == "anthropic":
        from proxy_anthropic import AnthropicProxy
        return AnthropicProxy
    elif provider_name == "openai":
        from proxy_openai import OpenAIProxy
        return OpenAIProxy
    elif provider_name == "llama":
        from proxy_llama import LlamaProxy
        return LlamaProxy


def get_sse_body(provider_name):
    if provider_name == "anthropic":
        return ANTHROPIC_SSE
    else:
        return OPENAI_SSE


async def create_proxy_app(proxy_cls, upstream_url, cm_port):
    """Create a proxy app instance pointing at a specific upstream."""
    from proxy_base import ProxyBase
    proxy = proxy_cls.__new__(proxy_cls)
    ProxyBase.__init__(
        proxy,
        upstream_url=upstream_url,
        proxy_port=0,
        tool_name=_default_tool(proxy_cls),
        cm_port=cm_port,
    )

    app = web.Application()
    app.router.add_get("/health", proxy.health)
    app.router.add_route("*", "/{path_info:.*}", proxy.handle_request)
    app["proxy"] = proxy
    return app


def _default_tool(proxy_cls):
    name = proxy_cls.__name__.lower()
    if "anthropic" in name:
        return "openclaw-anthropic"
    elif "llama" in name:
        return "llama-local"
    else:
        return "openclaw-openai"
