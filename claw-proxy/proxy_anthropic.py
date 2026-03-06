#!/usr/bin/env python3
"""claw-proxy-anthropic: Anthropic API proxy with token extraction."""

import os
import json
import logging

from proxy_base import ProxyBase

log = logging.getLogger(__name__)


class AnthropicProxy(ProxyBase):
    def __init__(self):
        super().__init__(
            upstream_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
            proxy_port=int(os.environ.get("CM_PROXY_ANTHROPIC_PORT", "14000")),
            tool_name=os.environ.get("CLAW_TOOL", "openclaw-anthropic"),
        )

    def extract_tokens(self, sse_lines):
        tokens_in = 0
        tokens_out = 0
        for line in sse_lines:
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "message_start":
                        tokens_in = data.get("message", {}).get("usage", {}).get("input_tokens", 0)
                    elif data.get("type") == "message_delta":
                        tokens_out = data.get("usage", {}).get("output_tokens", 0)
                except Exception:
                    pass
        return tokens_in, tokens_out


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    AnthropicProxy().run()
