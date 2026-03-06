# claw-proxy — Implementation & Rollout Plan

*Plan only. No implementation until approved.*

---

## What It Does

A lightweight HTTP proxy (`claw-proxy`) sits between OpenClaw and the model provider API (Anthropic/OpenAI). It:

1. Receives API calls from OpenClaw
2. Forwards them transparently to the real provider
3. Intercepts the streaming SSE response to extract token counts
4. Posts a token event to `/api/tokens` (fire-and-forget)
5. Returns the response to OpenClaw unchanged

OpenClaw sees no difference. The proxy is invisible unless it crashes.

---

## Architecture

```
OpenClaw gateway
     │
     │  HTTP POST /v1/messages  (currently goes to api.anthropic.com)
     ▼
claw-proxy  (localhost:14000)
     │
     ├──► Anthropic / OpenAI  (real API, full streaming response)
     │         │
     │    SSE stream (message_start → content_block_delta → message_delta)
     │         │
     │    extract: input_tokens, output_tokens, model, tool/session
     │         │
     ├──► POST localhost:CM_PORT/api/tokens  (fire-and-forget, never blocks)
     │
     └──► OpenClaw  (stream forwarded in real-time, zero added latency on happy path)
```

**Fail-open design (critical):**
- If the proxy can't reach Anthropic → returns the upstream error to OpenClaw (same as today)
- If the proxy crashes → OpenClaw gets `Connection refused` on `localhost:14000`; we revert config
- If `/api/tokens` POST fails → silently ignored; proxy still returns API response
- The proxy NEVER holds up the API response to wait for token reporting

---

## Implementation

**Language:** Python (async, aiohttp) — consistent with collector, handles SSE streaming cleanly  
**Location:** `claw-proxy/proxy.py`  
**Port:** `14000` (env: `CM_PROXY_PORT`, default 14000)  
**Systemd unit:** `claw-proxy.service` (user-level, same as collector and web)

### Token extraction — Anthropic SSE format

Anthropic streaming responses include:

```
event: message_start
data: {"type":"message_start","message":{"model":"claude-sonnet-4-6","usage":{"input_tokens":1523}}}

event: message_delta
data: {"type":"message_delta","usage":{"output_tokens":342}}
```

The proxy reads these two events, accumulates `input_tokens` and `output_tokens`, then posts after the stream closes.

### Tool/session attribution

The proxy reads the incoming request body to extract:
- `model` — from request JSON
- `tool` — from `X-Claw-Tool` request header (OpenClaw would need to send this), OR derived from the model name (e.g. `anthropic`)
- `session_id` — from `X-Claw-Session` header, if present

If no headers are present, tool defaults to `"openclaw"` and session_id is omitted. (This is the minimal viable approach; richer attribution requires OpenClaw to send headers, which is a separate decision.)

---

## Phase 1: Isolated Testing (before touching live system)

### Test infrastructure

A test harness with two mock servers:

1. **Mock upstream API** — a tiny HTTP server that returns realistic Anthropic SSE responses; can be configured to return errors, hang, etc.
2. **Mock token receiver** — a tiny HTTP server that records POST `/api/tokens` calls

### Tests to write FIRST (TDD — all must fail before proxy exists)

**Group A: Forwarding correctness**

| Test | What it checks |
|------|---------------|
| `test_proxy_forwards_post_body` | Request body reaches upstream unchanged |
| `test_proxy_forwards_auth_headers` | `Authorization` header passed through |
| `test_proxy_returns_non_streaming_response` | Non-streaming JSON response returned correctly |
| `test_proxy_streams_response_in_realtime` | SSE chunks arrive at client as upstream emits them (no buffering) |
| `test_proxy_preserves_status_codes` | 400/429/500 from upstream returned to client unchanged |

**Group B: Token extraction**

| Test | What it checks |
|------|---------------|
| `test_extracts_input_tokens_from_message_start` | Reads `input_tokens` from `message_start` event |
| `test_extracts_output_tokens_from_message_delta` | Reads `output_tokens` from `message_delta` event |
| `test_posts_token_event_after_stream_close` | Token event POSTed to `/api/tokens` after stream ends |
| `test_token_event_has_correct_model` | Model name from request matches token event |
| `test_token_event_session_id_from_header` | `X-Claw-Session` header ends up in token event |
| `test_no_token_post_if_stream_has_no_usage` | If upstream sends no usage events (e.g. error), no token POST |

**Group C: Fail-open behaviour (critical)**

| Test | What it checks |
|------|---------------|
| `test_upstream_down_returns_503` | If upstream is unreachable, proxy returns 503 to client (not hang) |
| `test_upstream_500_returned_to_client` | Upstream error code flows through |
| `test_token_reporter_down_does_not_block` | If `/api/tokens` is down, proxy still completes the API call |
| `test_token_reporter_timeout_does_not_block` | Token POST has 2s timeout; slow reporter doesn't hold up response |
| `test_concurrent_streams_do_not_mix_tokens` | Two simultaneous requests accumulate tokens independently |

**Group D: Operational**

| Test | What it checks |
|------|---------------|
| `test_health_endpoint` | `GET /health` returns `{"ok": true}` |
| `test_proxy_respects_CM_PROXY_PORT` | Binds to port from env var |
| `test_proxy_respects_upstream_url_env` | `ANTHROPIC_BASE_URL` override works |

### Run order (TDD loop)
Write all tests → confirm all FAIL → implement proxy → confirm all PASS → commit.

---

## Phase 2: Pre-Switchover Checklist (before touching live OpenClaw)

**Do all of these before changing any OpenClaw config:**

- [ ] `claw-proxy` service started and healthy: `curl http://localhost:14000/health`
- [ ] Proxy manually tested with a real Anthropic call (curl directly, not via OpenClaw):
  ```bash
  curl http://localhost:14000/v1/messages \
    -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"claude-haiku-4-5","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
  ```
  Expected: real Claude response, token event appears in DB
- [ ] SSH access independently verified: David confirms he can SSH to server via Tailscale
- [ ] Config backup taken:
  ```bash
  cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.pre-proxy-backup
  ```
- [ ] Rollback command ready and tested (dry run):
  ```bash
  cp ~/.openclaw/openclaw.json.pre-proxy-backup ~/.openclaw/openclaw.json
  systemctl --user restart openclaw-gateway
  ```

---

## Phase 3: Dead Man's Switch

**Before switching OpenClaw config**, set a cron job that auto-reverts after 10 minutes:

```bash
# Set via claw cron (or shell background job):
# After 10 min: cp backup → config → restart gateway
# Cancel immediately when switchover is confirmed working
```

This is the safety net. If the switch goes wrong and Signal goes down, the revert fires automatically and OpenClaw recovers without human intervention. Cancel the cron as soon as the first test message through the proxy succeeds.

Implementation: use `claw cron add` with a one-shot `at` job 10 minutes out, payload = systemEvent with the rollback instruction text. Or a shell background job:
```bash
(sleep 600 && cp ~/.openclaw/openclaw.json.pre-proxy-backup ~/.openclaw/openclaw.json && systemctl --user restart openclaw-gateway && echo "AUTO-REVERTED") &
REVERT_PID=$!
# ... do the switchover ...
# On success: kill $REVERT_PID
```

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

## Open Questions Before Implementation

1. **OpenAI support now or later?** The proxy can support both Anthropic and OpenAI format (different SSE token field names). Start Anthropic-only and add OpenAI later?

2. **Tool attribution** — for now, all token events get `tool="openclaw"`. If we want per-tool breakdown (e.g. `tool="claude-code"` vs `tool="openclaw-gateway"`), OpenClaw needs to send an `X-Claw-Tool` header. Is that a later problem?

3. **HTTPS upstream** — the proxy connects to `api.anthropic.com` over HTTPS. No change from today; proxy just adds a localhost hop.

4. **Proxy as gatekeeper** — once the proxy is in the path, it could enforce spend limits, log full request/response, etc. Out of scope for now but worth noting.

---

*Plan authored: 2026-03-06. Awaiting approval before any implementation.*
