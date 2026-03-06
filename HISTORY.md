# claw-monitor — Project History

---

## 2026-03-06 — Project Kickoff

### Context
David Williams requested a lightweight OpenClaw resource monitor. The project was initiated via Signal message at 06:33 PST.

### Requirements (as stated)
- Second-by-second (polling every 10s) monitoring of CPU, memory, and network I/O attributable to OpenClaw
- Token usage tracking for external LLM tool calls
- Dynamic process registration: OpenClaw fires a trivial one-shot API call when it starts using a new tool/agent/OS utility
- No LLM/AI involvement in the monitor itself
- Low-priority daemon (does not compete with Qwen or OpenClaw)
- Web dashboard: Next.js + Vite + React + Radix UI Themes
- Permanent port, accessible from all Tailscale-linked devices
- Data stored in a database (SQLite chosen for simplicity)
- Design-first: **no code until David approves the plan**

### Participants
- **DavidBot** (OpenClaw main session) — orchestrator, author of initial README/HISTORY
- **claw-monitor-builder** — spawned subagent managing Claude Code
- **Claude Code** — implementation agent (planning mode only until approval)

### Decisions Made (initial design)
- **Port:** 7432 (permanent, PM2-managed)
- **Collector language:** Python 3 + psutil (simplest for v1; Rust rewrite possible later)
- **Database:** SQLite (no infra overhead; better-sqlite3 in Next.js, sqlite3 in Python)
- **API:** REST (Next.js API routes) — simple, debuggable, easy for shell curl calls
- **Dashboard:** Next.js App Router + Radix UI Themes + Recharts
- **OpenClaw integration:** fire-and-forget `curl ... &` shell call, wrapped in `scripts/register-tool.sh`
- **Live updates:** SSE (Server-Sent Events) at 10s refresh
- **Tailscale access:** `http://dw-asus-linux.tail3eef35.ts.net:7432`

### Open Questions (pending David's review)
1. Python vs Rust for collector?
2. Token cost tracking (raw counts only, or compute USD in dashboard)?
3. Data retention policy (suggest: 7 days full-res, forever hourly)?
4. Auth on port 7432 (suggest: Tailscale-only, no app auth)?
5. PM2 vs systemd for Next.js process manager?
6. SSE vs WebSocket for dashboard live updates?

### Status
- [x] Repo created by David
- [x] README.md written (architecture, schema, file layout)
- [x] HISTORY.md started
- [ ] Claude Code planning session — in progress
- [ ] David reviews plan
- [ ] Implementation approved
- [ ] Build
- [ ] Test
- [ ] Deploy

---

*Future entries appended below as the project progresses.*
