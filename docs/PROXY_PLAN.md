# claw-proxy — Implementation & Rollout Plan

*Plan only. No implementation until approved.*

---

## What It Does

Three separate lightweight HTTP proxies, one per provider. Each proxy knows exactly one provider's wire format and SSE token schema. No routing logic, no format negotiation — just forward and extract.

| Proxy | Port | Upstream | SSE format |
|-------|------|----------|-----------|
| `claw-proxy-anthropic` | 14000 | `api.anthropic.com` | `message_start` / `message_delta` |
| `claw-proxy-openai` | 14001 | `api.openai.com` | `usage` field in final `data: [DONE]` chunk |
| `claw-proxy-llama` | 14002 | `localhost:19434` | OpenAI-compatible (same as above, local) |

Each proxy:
1. Receives API calls from OpenClaw
2. Forwards them transparently to its upstream
3. Intercepts the streaming SSE response to extract token counts
4. Posts a token event to `/api/tokens` (fire-and-forget)
5. Returns the response to OpenClaw unchanged

OpenClaw sees no difference. Each proxy is invisible unless it crashes.

---

## Architecture

```
OpenClaw gateway
     ├── anthropic provider ──► claw-proxy-anthropic (localhost:14000) ──► api.anthropic.com
     ├── openai provider    ──► claw-proxy-openai    (localhost:14001) ──► api.openai.com
     └── llama provider     ──► claw-proxy-llama     (localhost:14002) ──► localhost:19434

Each proxy:
     │
     │  intercepts SSE stream
     │  extracts input_tokens + output_tokens
     │
     └──► POST localhost:CM_PORT/api/tokens  (fire-and-forget, never blocks)
```

**Fail-open design (critical — applies to all three):**
- If the proxy can't reach upstream → returns upstream error to OpenClaw (same as direct today)
- If the proxy crashes → OpenClaw gets `Connection refused`; revert config for that provider
- If `/api/tokens` POST fails → silently ignored; proxy still returns API response
- The proxy NEVER holds up the API response to wait for token reporting

---

## Implementation

**Language:** Python (async, aiohttp) — consistent with collector, handles SSE streaming cleanly  
**Location:** `claw-proxy/` directory, one file per provider  
**Systemd units:** `claw-proxy-anthropic.service`, `claw-proxy-openai.service`, `claw-proxy-llama.service` (all user-level)

### Token extraction — per-provider SSE format

**Anthropic** (`proxy_anthropic.py`, port 14000):
```
event: message_start
data: {"type":"message_start","message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":1523}}}

event: message_delta
data: {"type":"message_delta","usage":{"output_tokens":342}}
```
Accumulate `input_tokens` from `message_start`, `output_tokens` from `message_delta`. Post after stream closes.

**OpenAI** (`proxy_openai.py`, port 14001):
```
data: {"id":"...","choices":[...],"usage":{"prompt_tokens":150,"completion_tokens":80,"total_tokens":230}}
data: [DONE]
```
OpenAI sends `usage` in the final chunk before `[DONE]`. Extract `prompt_tokens` → `tokens_in`, `completion_tokens` → `tokens_out`.

**Llama.cpp** (`proxy_llama.py`, port 14002):
```
data: {"choices":[...],"usage":{"prompt_tokens":150,"completion_tokens":80}}
```
Same OpenAI-compatible format. Upstream is `localhost:19434` (the local llama-server). Tool defaults to `"llama-local"`.

### Tool/session attribution (all proxies)

- `model` — from request JSON body
- `tool` — from `X-Claw-Tool` request header if present; else proxy name (`"openclaw-anthropic"`, `"openclaw-openai"`, `"llama-local"`)
- `session_id` — from `X-Claw-Session` header, if present

---

## Phase 1: Isolated Testing (before touching live system)

Tests cover all three proxies. Phase 3 & 4 (live switchover) covers Anthropic only.

### Test infrastructure

A shared test harness (`claw-proxy/tests/conftest.py`) with:

1. **Mock upstream API** — a tiny aiohttp server per provider, returns realistic SSE responses; configurable to return errors, hang, drop mid-stream, etc.
2. **Mock token receiver** — a tiny HTTP server that records POST `/api/tokens` calls for assertion

### Tests to write FIRST (TDD — all must fail before any proxy exists)

**Group A: Forwarding correctness** (run against all three proxies via parametrize)

| Test | What it checks |
|------|---------------|
| `test_proxy_forwards_post_body[anthropic\|openai\|llama]` | Request body reaches upstream unchanged |
| `test_proxy_forwards_auth_headers[anthropic\|openai\|llama]` | `Authorization` header passed through |
| `test_proxy_returns_non_streaming_response[anthropic\|openai\|llama]` | Non-streaming JSON response returned correctly |
| `test_proxy_streams_response_in_realtime[anthropic\|openai\|llama]` | SSE chunks arrive at client as upstream emits them (no buffering) |
| `test_proxy_preserves_status_codes[anthropic\|openai\|llama]` | 400/429/500 from upstream returned to client unchanged |

**Group B: Token extraction — Anthropic**

| Test | What it checks |
|------|---------------|
| `test_anthropic_extracts_input_tokens_from_message_start` | Reads `input_tokens` from `message_start` event |
| `test_anthropic_extracts_output_tokens_from_message_delta` | Reads `output_tokens` from `message_delta` event |
| `test_anthropic_posts_token_event_after_stream_close` | Token event POSTed to `/api/tokens` after stream ends |
| `test_anthropic_token_event_has_correct_model` | Model name from request matches token event |
| `test_anthropic_token_event_session_id_from_header` | `X-Claw-Session` header ends up in token event |
| `test_anthropic_no_token_post_on_error_stream` | If upstream sends error (no usage events), no token POST |

**Group C: Token extraction — OpenAI**

| Test | What it checks |
|------|---------------|
| `test_openai_extracts_tokens_from_final_usage_chunk` | Reads `prompt_tokens` / `completion_tokens` from final SSE chunk |
| `test_openai_posts_token_event_after_done` | Token event posted after `data: [DONE]` |
| `test_openai_token_event_has_correct_model` | Model name from request matches token event |
| `test_openai_no_token_post_if_no_usage_field` | Some OpenAI responses omit usage; no crash, no post |

**Group D: Token extraction — Llama.cpp**

| Test | What it checks |
|------|---------------|
| `test_llama_extracts_tokens_openai_compatible` | Same format as OpenAI; upstream is localhost:19434 |
| `test_llama_tool_defaults_to_llama_local` | No `X-Claw-Tool` header → tool=`"llama-local"` in event |
| `test_llama_upstream_is_local_not_remote` | Proxy targets `localhost:19434`, not any external URL |

**Group E: Fail-open behaviour (critical — all proxies)**

| Test | What it checks |
|------|---------------|
| `test_upstream_down_returns_503[anthropic\|openai\|llama]` | Upstream unreachable → 503 to client, no hang |
| `test_upstream_500_returned_to_client[anthropic\|openai\|llama]` | Upstream error code flows through unchanged |
| `test_token_reporter_down_does_not_block[anthropic\|openai\|llama]` | `/api/tokens` down → proxy still completes API call |
| `test_token_reporter_timeout_does_not_block[anthropic\|openai\|llama]` | Token POST has 2s timeout; slow reporter never holds up response |
| `test_concurrent_streams_do_not_mix_tokens[anthropic\|openai\|llama]` | Two simultaneous requests accumulate tokens independently |

**Group F: Operational (all proxies)**

| Test | What it checks |
|------|---------------|
| `test_health_endpoint[anthropic\|openai\|llama]` | `GET /health` returns `{"ok": true}` |
| `test_proxy_respects_port_env[anthropic\|openai\|llama]` | Binds to port from env var |
| `test_proxy_respects_upstream_url_env[anthropic\|openai\|llama]` | Upstream URL override via env var works |

### Run order (TDD loop)
Write all tests → confirm all FAIL → implement proxies → confirm all PASS → commit.

---

## Phase 2: Pre-Switchover Checklist (before touching live OpenClaw)

All three proxies are tested here, but only Anthropic goes live in Phase 4.

**Do all of these before changing any OpenClaw config:**

- [ ] All three proxies started and healthy:
  ```bash
  curl http://localhost:14000/health  # anthropic
  curl http://localhost:14001/health  # openai
  curl http://localhost:14002/health  # llama (only if llama-server running)
  ```
- [ ] Each proxy manually tested with a real API call (curl directly, not via OpenClaw):
  ```bash
  # Anthropic
  curl http://localhost:14000/v1/messages \
    -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"claude-haiku-4-5","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
  # Expected: real Claude response, token event in DB

  # OpenAI
  curl http://localhost:14001/v1/chat/completions \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"gpt-4o-mini","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
  # Expected: real GPT response, token event in DB

  # Llama (only if llama-server running)
  curl http://localhost:14002/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"qwen3-35b","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
  # Expected: local model response, token event in DB with tool="llama-local"
  ```
- [ ] SSH access independently verified: David confirms he can SSH to server via Tailscale (`ssh david@dw-asus-linux.tail3eef35.ts.net`)
- [ ] Config backup taken:
  ```bash
  cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.pre-proxy-backup
  ```
- [ ] Rollback command staged (run this to revert instantly):
  ```bash
  cp ~/.openclaw/openclaw.json.pre-proxy-backup ~/.openclaw/openclaw.json && systemctl --user restart openclaw-gateway
  ```

---

## Phase 3: Dead Man's Switch

**Before switching OpenClaw config**, start a 2-minute auto-revert timer.

```bash
(sleep 120 && cp ~/.openclaw/openclaw.json.pre-proxy-backup ~/.openclaw/openclaw.json && systemctl --user restart openclaw-gateway && echo "AUTO-REVERTED") &
REVERT_PID=$!
echo "Dead man's switch armed. PID=$REVERT_PID. Cancel with: kill $REVERT_PID"
```

This is the safety net. If Signal goes dark after the switch, the revert fires automatically after 2 minutes and OpenClaw recovers without human intervention.

**Cancel immediately** when the first test message confirms everything works:
```bash
kill $REVERT_PID && echo "Dead man's switch cancelled — switchover confirmed good"
```

**Why 2 minutes:** Long enough to send a test message and get a response. Short enough that if something goes wrong, Signal is back quickly.

---

## Phase 4: The Switchover

**Do this with David present and watching Signal.**

1. Confirm proxy is running: `systemctl --user status claw-proxy`
2. Start dead man's switch (10 min revert timer)
3. Update OpenClaw config to point at proxy:
   ```json
   {
     "models": {
       "providers": {
         "anthropic": {
           "baseUrl": "http://localhost:14000"
         }
       }
     }
   }
   ```
4. Restart gateway: `systemctl --user restart openclaw-gateway`
5. **David sends a test message via Signal** — something short
6. Verify:
   - David got a response ✅
   - Token event appears in DB: `SELECT * FROM token_events ORDER BY ts DESC LIMIT 1`
   - Dashboard shows non-zero tok/min
7. Cancel dead man's switch
8. Done

**If step 6 fails at any point:** run rollback command immediately (or let dead man's switch fire). OpenClaw recovers, proxy can be debugged offline.

---

## Rollback Procedure (if things go wrong)

```bash
# Option A: SSH into server (preferred)
cp ~/.openclaw/openclaw.json.pre-proxy-backup ~/.openclaw/openclaw.json
systemctl --user restart openclaw-gateway
# OpenClaw is back on direct Anthropic — Signal works again

# Option B: Dead man's switch fires automatically after 10 min
# No action needed

# Option C: Stop proxy only (OpenClaw gets connection refused → errors, but no lockout)
systemctl --user stop claw-proxy
# Then do Option A
```

---

## What Changes in OpenClaw Config

Minimal change — just `baseUrl` for the anthropic provider:

```json
{
  "models": {
    "providers": {
      "anthropic": {
        "baseUrl": "http://localhost:14000"
      }
    }
  }
}
```

Everything else stays the same. The proxy uses the real `ANTHROPIC_API_KEY` from the environment — it reads from the same env var OpenClaw sets.

---

## Scope Summary

| Phase | Anthropic | OpenAI | Llama |
|-------|-----------|--------|-------|
| Phase 1 (tests) | ✅ | ✅ | ✅ |
| Phase 2 (manual curl test) | ✅ | ✅ | ✅ (if running) |
| Phase 3 (dead man's switch) | ✅ | — | — |
| Phase 4 (live switchover) | ✅ | deferred | deferred |

OpenAI and Llama proxies are fully built and tested but not wired into OpenClaw until Anthropic is confirmed stable in production.

## Notes

- **Tool attribution** — default `tool` values: `"openclaw-anthropic"`, `"openclaw-openai"`, `"llama-local"`. Richer per-tool breakdown (e.g. `tool="claude-code"`) requires `X-Claw-Tool` header — deferred.
- **HTTPS upstream** — Anthropic and OpenAI proxies connect over HTTPS to the real APIs. Llama proxy is plain HTTP to localhost. No SSL termination needed.
- **Proxy as gatekeeper** — once in the path, could enforce spend limits, full logging, etc. Out of scope for now.

---

*Plan authored: 2026-03-06. Awaiting approval before any implementation.*
