# claw-monitor TODO

Last updated: 2026-03-06

---

## 🔥 Next Session — Do First

### Phase 3+4: Live Anthropic Proxy Switchover
**David must be present and watching Signal.**

```bash
# 1. Load API key
source ~/.bashrc
echo $ANTHROPIC_API_KEY  # confirm it's set

# 2. Start proxy
systemctl --user start claw-proxy-anthropic
curl http://localhost:14000/health  # must return {"ok":true}

# 3. Manual curl test (real API call through proxy)
curl -s http://localhost:14000/v1/messages \
  -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-haiku-4-5","max_tokens":20,"stream":true,"messages":[{"role":"user","content":"say hi"}]}'
# Then verify DB: python3 -c "import sqlite3; c=sqlite3.connect('/home/david/.openclaw/claw-monitor/metrics.db'); print(c.execute('SELECT * FROM token_events ORDER BY ts DESC LIMIT 3').fetchall())"

# 4. Arm dead man's switch (2 min auto-revert)
cp ~/.openclaw/openclaw.json ~/.openclaw/openclaw.json.pre-proxy-backup
(sleep 120 && cp ~/.openclaw/openclaw.json.pre-proxy-backup ~/.openclaw/openclaw.json && systemctl --user restart openclaw-gateway && echo "AUTO-REVERTED") &
REVERT_PID=$!
echo "Dead man's switch armed. PID=$REVERT_PID"

# 5. Apply config change (see below)
# 6. Restart gateway
systemctl --user restart openclaw-gateway

# 7. David sends a test Signal message — watch for response + tok/min in dashboard

# 8. On success: cancel dead man's switch
kill $REVERT_PID && echo "Cancelled — all good"

# 9. Enable for auto-start
systemctl --user enable claw-proxy-anthropic
```

**OpenClaw config change** (step 5):
Use `openclaw gateway config.get` to see current config, then `config.patch` to add:
```json
{ "models": { "providers": { "anthropic": { "baseUrl": "http://localhost:14000" } } } }
```

**Rollback if needed:**
```bash
cp ~/.openclaw/openclaw.json.pre-proxy-backup ~/.openclaw/openclaw.json
systemctl --user restart openclaw-gateway
```

---

## 📋 Pending Work

### Token Proxies
- [ ] **Anthropic proxy live** (Phase 3+4 above)
- [ ] OpenAI proxy live (same process, after Anthropic confirmed stable)
- [ ] Llama proxy live (only when Qwen server is running)

### UI / Dashboard
- [ ] **Overview page** — review live with David (was redesigned today, needs eyes-on review)
- [ ] Metrics page — currently shows empty charts; time range picker may be broken
- [ ] Tokens page — only has test data; will populate once proxy is live
- [ ] All pages — systematic review for bugs/missing features (David planned this session)
- [ ] Tag markers on Metrics page (same as Overview — carry the design through)

### Tests
- [ ] Run full test suite against the live system after proxy goes live: `./run-tests.sh --integration`
- [ ] Add proxy tests to `run-tests.sh` (currently separate in `claw-proxy/tests/`)

### Documentation
- [ ] Update README with proxy setup instructions
- [ ] Update INSTRUCTIONS.md — note that `register-tool.sh tokens` is now also auto-covered by the proxy (no need to call manually once proxy is live)

### Infrastructure
- [ ] Consider: `systemctl --user enable claw-proxy-openai claw-proxy-llama` (start on boot)
- [ ] Consider: add proxy health to heartbeat checks

---

## ✅ Completed (2026-03-06)

- GitHub fine-grained PAT for claw-monitor repo
- Full test plan (TEST_PLAN.md, 3 rounds of review)
- All tests implemented — 11 groups, ~173 tests
- Integration tests reworked — real HTTP server, fully self-contained
- `run-tests.sh` one-liner
- `CM_PORT` placeholder throughout docs
- Bug fix: `register-tool.sh tokens` sub-command (TDD)
- TDD-first mandate documented in TEST_PLAN.md §0.4
- Overview page redesign — spec + implementation
- docs/UI_SPEC.md
- docs/PROXY_PLAN.md
- claw-proxy — Anthropic/OpenAI/Llama, 52 tests, systemd units installed
