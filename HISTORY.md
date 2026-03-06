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
- Web dashboard: Next.js + React + Radix UI Themes + Recharts
- Permanent port, accessible from all Tailscale-linked devices
- Data stored in a database (SQLite chosen for simplicity)
- Design-first: **no code until David approves the plan**

### Participants
- **DavidBot** (OpenClaw main session) — orchestrator, author of initial README/HISTORY
- **claw-monitor-builder** — spawned subagent managing Claude Code planning session
- **Claude Code** — architecture reviewer (planning mode only until approval)

### Initial Design Decisions
- **Port:** 7432 (permanent, systemd-managed)
- **Collector language:** Python 3 + psutil (simplest for v1; Rust rewrite possible later)
- **Database:** SQLite (no infra overhead; better-sqlite3 in Next.js, sqlite3 in Python)
- **API:** REST (Next.js API routes) — simple, debuggable, easy for shell curl calls
- **Dashboard:** Next.js App Router + Radix UI Themes + Recharts
- **OpenClaw integration:** fire-and-forget `curl ... &` shell call, wrapped in `scripts/register-tool.sh`
- **Live updates:** SSE (Server-Sent Events) at ~10s refresh
- **Tailscale access:** `http://dw-asus-linux.tail3eef35.ts.net:7432`

---

## 2026-03-06 — Claude Code Architecture Review

### Session Summary
Claude Code reviewed the initial architecture and provided detailed analysis, component specifications, and recommendations on all open questions.

### Architecture Issues Identified and Resolved

#### 1. PID Reuse (Critical Correctness Bug)
**Problem:** Linux recycles PIDs. Original schema used `pid INTEGER PRIMARY KEY` — if an OpenClaw process died and an unrelated process got the same PID, the collector would attribute the wrong process's resources to OpenClaw. Worse, the new registration would collide with the old DB row.

**Fix:**
- `process_registry` table now uses `id INTEGER PRIMARY KEY AUTOINCREMENT` (not `pid`)
- `pid` is a regular column with a non-unique index
- Collector verifies `/proc/<pid>/comm` matches the registered `name` before trusting a PID
- If comm mismatch detected → marks old row `unregistered`, ignores new (unrelated) process

#### 2. Per-PID Network I/O Not Feasible
**Problem:** Original design referenced `/proc/<pid>/net/dev` for per-PID network accounting. That file shows per-interface stats for the entire network namespace, not per-PID.

**Per-PID net requires:** Either netfilter/cgroups (heavy) or libpcap + /proc correlation (complex).

**Fix:** Network I/O collected machine-wide from `/proc/net/dev`. Stored in dedicated rows where `grp='machine'`. Per-group net columns removed from the schema. v2 candidate for per-PID net (cgroups or eBPF).

#### 3. CPU Percentage Needs Delta Calculation
**Problem:** `/proc/<pid>/stat` gives cumulative CPU ticks, not percentages. CPU% must be computed from delta between two readings: `(ticks_now - ticks_prev) / (elapsed_s * cpu_count)`.

**Implication:** The first sample after PID registration has no CPU data. `cpu_pct` is NULL for that row. Documented as expected behavior.

#### 4. SQLite WAL Mode Required for Concurrent Access
**Problem:** Python collector writes every 10s; Next.js API reads concurrently. Without WAL mode, this causes `SQLITE_BUSY` errors under load.

**Fix:** Both Python and Node.js must explicitly set `PRAGMA journal_mode=WAL` when opening the database. Added to schema.sql (applied on init) and documented in both component specs.

#### 5. Wrong API Path in File Layout
**Problem:** README showed `src/api/` but Next.js App Router puts API routes at `src/app/api/`.

**Fix:** Corrected to `src/app/api/` throughout.

#### 6. Token Events Lacked Session Correlation
**Problem:** No way to answer "how many tokens did session X consume?" — no `session_id` field.

**Fix:** Added `session_id TEXT` column to `token_events`. Optional field; matches OpenClaw session format (e.g., `agent:main:signal:direct:+15303386428`).

### Open Questions — Resolved

| Question | Decision | Rationale |
|---|---|---|
| Python vs Rust for collector? | **Python** | I/O-bound operation; psutil handles /proc robustly; <200 lines; Rust saves nothing measurable |
| Token cost storage? | **Raw counts only** | Pricing changes frequently (3x in 18 months); compute USD in dashboard via `pricing.json`; drop `cost_usd` column from schema |
| Data retention? | **14 days full-res, daily aggregates forever** | ~35 MB for 14 days (10s/6 groups/50 bytes); daily sufficient for historical trends older than 1 month; changed from 7 days to 14 days |
| Auth on port 7432? | **Tailscale + IP range middleware** | Tailscale = network auth; add 5-line middleware rejecting requests outside 100.64.0.0/10 and 127.0.0.1 as defense-in-depth |
| PM2 vs systemd? | **systemd (user scope)** | Collector already uses systemd; consistent tooling; no extra deps; native log rotation; `systemctl --user status claw-*` shows both |
| WebSocket vs SSE? | **SSE** | Unidirectional push; native to Next.js; `EventSource` auto-reconnects; 10s interval means no latency need for WebSocket |

### Schema Changes (vs. initial design)

1. `process_registry`: PK changed from `pid` to autoincrement `id`; `pid` becomes regular indexed column
2. `token_events`: `cost_usd` column dropped; `model` made `NOT NULL`; `session_id TEXT` column added
3. New `metrics_daily` table added for long-term aggregates
4. `metrics` table: network columns (`net_in_kb`, `net_out_kb`) only populated on rows where `grp='machine'`; removed from per-group rows

### New Content Added to README

- Detailed collector core loop (pseudocode)
- PID auto-grouping rules table
- Known limitations section
- Full API specification with request/response schemas for all 6 endpoints
- Complete file layout with per-file descriptions
- OpenClaw integration protocol (exact curl commands, timing, format)
- Failure mode table
- Dashboard wireframes (ASCII) for all 4 pages
- Step-by-step deployment instructions
- systemd unit structure notes
- Day-to-day operations commands

### Status After Planning Session
- [x] Repo created by David
- [x] README.md written (initial architecture)
- [x] HISTORY.md started
- [x] Claude Code architecture review complete
- [x] All open questions resolved with recommendations
- [x] README.md expanded with full design detail
- [x] HISTORY.md updated with all decisions
- [ ] **David reviews and approves plan** ← current step
- [ ] Implementation begins
- [ ] Testing
- [ ] Deployment

---

## 2026-03-06 — Adaptive Polling Requirement Added

### Context
David raised a new requirement at 06:47 PST (before implementation started): rather than a fixed 10s poll interval, the collector should use an **adaptive interval** that slows during idle periods and speeds up during active ones. Goal: avoid an "absolute mountain of data" while keeping granularity where it matters.

### Design Discussion

**Signaling mechanism options considered:**
1. **Self-detecting** (chosen) — collector observes openclaw-gateway CPU% from the previous sample to decide the next interval. Zero coupling, zero overhead on OpenClaw, no new API endpoints.
2. Activity endpoint — OpenClaw POSTs `/api/activity` level. Rejected: adds coupling and still needs a CPU proxy anyway.
3. File-based heartbeat — OpenClaw touches a file; collector checks mtime. Rejected: fragile, same coupling issue.

### Decision: Self-Detecting Adaptive Intervals

| Gateway CPU% (prev sample) | Consecutive idle samples | Next interval |
|---|---|---|
| > 40% | any | **5s** (heavy activity) |
| 15–40% | any | **10s** (active) |
| 2–15% | any | **30s** (light / heartbeat) |
| < 2% | 1–2 | **30s** (transitioning to idle) |
| < 2% | 3+ | **60s** (deep idle) |

### Data Sparsity Handling

Sparse/irregular intervals require time-scale x-axis in charts (not sequential index). Recharts handles this via `XAxis dataKey="ts" type="number" scale="time"`. Idle gaps display as honest time gaps in charts.

**Schema addition:** `sample_interval_s INTEGER` column added to `metrics` table. Records actual elapsed seconds per sample. Enables "data density" indicator in dashboard UI.

### HISTORY.md Confirmation
David asked: "Just to confirm you are putting the history of this design process and of the future implementation process into history.MD right?"

**Yes.** Every design decision, every architecture change, every significant conversation goes into `HISTORY.md`. This is the living record of how the project got where it is. Implementation decisions and debugging notes will be added as the project proceeds.

### README Changes
- Description updated to reference adaptive polling
- Goal 3 updated ("adaptive poll interval, 5s–60s")
- Architecture overview updated
- Collector component spec replaced with full adaptive polling spec:
  - Interval table (CPU% thresholds → target intervals)
  - Data sparsity implications
  - `sample_interval_s` schema addition
  - Updated core loop pseudocode (now includes adaptive interval logic)
- Known Limitations updated (PID churn window now "5–60s" not "10s")

---

*Future entries appended below as the project progresses.*
