"""claw-proxy base: shared HTTP proxy logic with token extraction."""

import os
import asyncio
import json
import logging

import aiohttp
from aiohttp import web

log = logging.getLogger(__name__)

SKIP_HEADERS = frozenset(("host", "content-length", "transfer-encoding"))


class ProxyBase:
    def __init__(self, upstream_url, proxy_port, tool_name, cm_port=7432):
        self.upstream_url = upstream_url.rstrip("/")
        self.proxy_port = proxy_port
        self.tool_name = tool_name
        self.cm_port = cm_port

    async def handle_request(self, request):
        path = request.match_info.get("path_info", "")
        upstream = f"{self.upstream_url}/{path}"
        if request.query_string:
            upstream += f"?{request.query_string}"

        body = await request.read()
        model = "unknown"
        try:
            model = json.loads(body).get("model", "unknown")
        except Exception:
            pass

        session_id = request.headers.get("X-Claw-Session")
        tool = request.headers.get("X-Claw-Tool", self.tool_name)
        headers = {k: v for k, v in request.headers.items()
                   if k.lower() not in SKIP_HEADERS}

        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.request(
                    request.method, upstream,
                    headers=headers, data=body,
                    allow_redirects=False,
                ) as resp:
                    ct = resp.headers.get("Content-Type", "")
                    if "text/event-stream" in ct:
                        return await self._handle_streaming(
                            resp, request, tool, model, session_id)
                    else:
                        resp_body = await resp.read()
                        resp_headers = {
                            k: v for k, v in resp.headers.items()
                            if k.lower() not in ("transfer-encoding", "content-length")
                        }
                        return web.Response(
                            status=resp.status, body=resp_body, headers=resp_headers)
        except aiohttp.ClientConnectorError:
            return web.Response(status=503, text="Upstream unavailable")
        except Exception as e:
            log.error("handle_request error: %s", e)
            return web.Response(status=502, text="Proxy error")

    async def _handle_streaming(self, upstream_resp, request, tool, model, session_id):
        resp_headers = {
            k: v for k, v in upstream_resp.headers.items()
            if k.lower() not in ("transfer-encoding", "content-length")
        }
        response = web.StreamResponse(status=upstream_resp.status, headers=resp_headers)
        await response.prepare(request)

        sse_lines = []
        async for chunk in upstream_resp.content:
            await response.write(chunk)
            decoded = chunk.decode("utf-8", errors="replace")
            for line in decoded.split("\n"):
                stripped = line.rstrip("\r")
                if stripped:
                    sse_lines.append(stripped)

        await response.write_eof()

        try:
            tokens_in, tokens_out = self.extract_tokens(sse_lines)
            if tokens_in > 0 or tokens_out > 0:
                asyncio.ensure_future(
                    self.post_token_event(tool, model, tokens_in, tokens_out, session_id))
        except Exception as e:
            log.error("extract_tokens error: %s", e)

        return response

    def extract_tokens(self, sse_lines):
        raise NotImplementedError

    async def post_token_event(self, tool, model, tokens_in, tokens_out, session_id=None):
        payload = {
            "tool": tool,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
        if session_id:
            payload["session_id"] = session_id
        try:
            async with aiohttp.ClientSession() as sess:
                async with sess.post(
                    f"http://localhost:{self.cm_port}/api/tokens",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=2),
                ):
                    pass
        except Exception as e:
            log.debug("post_token_event failed (ignored): %s", e)

    async def health(self, request):
        return web.json_response({"ok": True})

    def run(self):
        app = web.Application()
        app.router.add_get("/health", self.health)
        app.router.add_route("*", "/{path_info:.*}", self.handle_request)
        web.run_app(app, host="127.0.0.1", port=self.proxy_port)
