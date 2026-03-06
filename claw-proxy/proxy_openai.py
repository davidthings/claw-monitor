#!/usr/bin/env python3
"""claw-proxy-openai: OpenAI API proxy with token extraction."""

import os
import json
import logging

from proxy_base import ProxyBase

log = logging.getLogger(__name__)


class OpenAIProxy(ProxyBase):
    def __init__(self):
        super().__init__(
            upstream_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com"),
            proxy_port=int(os.environ.get("CM_PROXY_OPENAI_PORT", "14001")),
            tool_name=os.environ.get("CLAW_TOOL", "openclaw-openai"),
        )

    def extract_tokens(self, sse_lines):
        return self._extract_openai_tokens(sse_lines)

    @staticmethod
    def _extract_openai_tokens(sse_lines):
        tokens_in = 0
        tokens_out = 0
        for line in sse_lines:
            if line.startswith("data: ") and line.strip() != "data: [DONE]":
                try:
                    data = json.loads(line[6:])
                    usage = data.get("usage")
                    if usage:
                        tokens_in = usage.get("prompt_tokens", 0)
                        tokens_out = usage.get("completion_tokens", 0)
                except Exception:
                    pass
        return tokens_in, tokens_out


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    OpenAIProxy().run()
