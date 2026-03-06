#!/usr/bin/env python3
"""claw-proxy-llama: Llama.cpp API proxy (OpenAI-compatible format)."""

import os
import logging

from proxy_openai import OpenAIProxy
from proxy_base import ProxyBase

log = logging.getLogger(__name__)


class LlamaProxy(ProxyBase):
    def __init__(self):
        super().__init__(
            upstream_url=os.environ.get("LLAMA_BASE_URL", "http://localhost:19434"),
            proxy_port=int(os.environ.get("CM_PROXY_LLAMA_PORT", "14002")),
            tool_name="llama-local",
        )

    def extract_tokens(self, sse_lines):
        return OpenAIProxy._extract_openai_tokens(sse_lines)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    LlamaProxy().run()
