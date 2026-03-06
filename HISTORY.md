# claw-monitor — Project History

## Attribution Convention

Each entry notes who did what at a high level:
- **David** — product owner; defines requirements and approves design
- **DavidBot** — OpenClaw main session; orchestrator; writes/updates design docs; incorporates David's feedback
- **claw-monitor-builder** — OpenClaw subagent spawned by DavidBot; manages Claude Code; routes concerns upward
- **Claude Code** — implementation agent; performs architecture review; will write all code once approved

---

## 2026-03-06 — Project Kickoff

### Context
David Williams requested a lightweight OpenClaw resource monitor. The project was initiated via Signal message at 06:33 PST.

**Who did what:** David defined requirements. DavidBot wrote the initial README.md and HISTORY.md, spawned claw-monitor-builder, committed to repo.

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

**Who did what:** claw-monitor-builder directed the session. Claude Code performed the architecture review, identified the bugs below, and resolved all open questions. DavidBot incorporated results into README.md and HISTORY.md.

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

**Who did what:** David raised the requirement. DavidBot designed the self-detecting approach and documented it in README. No Claude Code involvement.

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

## 2026-03-06 — David's Design Review Round 2 (07:14 PST)

**Who did what:** David reviewed the plan and raised 7 new requirements. DavidBot incorporated all of them into a full README rewrite and updated HISTORY. No Claude Code involvement in this round.

### Requirements Added / Clarified

#### 1. Agent Collaboration Documentation
**Requirement:** Document how DavidBot, claw-monitor-builder, and Claude Code are working together. HISTORY.md should attribute who did what at a high level.

**Done:** Added "Agent Collaboration" section to README with role table and decision authority description. Added "Attribution Convention" block to the top of HISTORY.md. Prior entries updated with "Who did what" callouts.

#### 2. OpenClaw Integration: Minimal Coupling + Remembering Problem
**Requirement:** Clarify that the integration should not be onerous or influence token consumption. OpenClaw should tell the tool the *kind* of thing it's doing and let the tool infer attribution from /proc. Address the problem of forgetting to report.

**Design response:**
- Renamed concept to "Minimal Coupling" principle: collector autodiscovers all PIDs from /proc; OpenClaw does NOT need to report individual processes for resource attribution.
- OpenClaw provides only two things: **tags** (work type) and **token counts** (invisible to OS).
- Detailed "Remembering Problem" table added to README showing reliability by trigger type: HIGH for session start and agent spawn, MEDIUM for mid-session type changes, LOW for session end.
- Mitigation: tags are "until next tag" semantics — a missed update extends the previous tag slightly, not a data loss.
- Two lines to be added to AGENTS.md startup routine to remind DavidBot to tag at conversation start.

#### 3. File System Monitoring
**Requirement:** Include disk/storage stats — how much space OpenClaw is taking up including log files. Exclude the monitor itself.

**Design response:**
- New `disk_snapshots` table added to schema.
- New `/api/disk` endpoint.
- New `disk_tracker.py` module using os.walk().
- New `/disk` dashboard page with stacked bar chart by directory.
- Tracked: `~/.openclaw/workspace`, `~/.openclaw/sessions`, `~/.openclaw/media`, `~/.openclaw/logs`, `~/.openclaw/claw-monitor`, `~/.openclaw` (total). journald log size via `journalctl --disk-usage`.
- **Excluded:** `~/work/claw-monitor/` (the tool itself).
- Written every 60s regardless of activity (disk growth is always relevant).

#### 4. Adaptive Collection: 1s Sweep, Write-Gated
**Requirement:** The 1s sweep can always run. Just don't write to DB every second when idle. This reduces risk of missing short activity bursts.

**Design response:**
- Replaced the "adaptive interval" model with a "sweep vs write" separation:
  - **Fast loop always runs at 1s** (reads CPU, mem, net, GPU into memory)
  - **Write gate:** write to DB if any OpenClaw PID has CPU% > 2% (activity) OR if last write was ≥60s ago (idle heartbeat)
  - **Idle heartbeat:** writes one row per 60s with `is_idle_heartbeat=1` — marks "still idle, nothing happened" so gaps are distinguishable from missing data
- Disk stats: 60s slow loop, separate from fast loop (os.walk is expensive)
- Added `is_idle_heartbeat INTEGER DEFAULT 0` column to metrics schema.
- `sample_interval_s` now reflects actual elapsed time since last write, not a target.

#### 5. GPU Monitoring
**Requirement:** Include GPU use in v1 (David expected this would be v2 but now wants it from the start).

**Design response:**
- Added GPU monitoring via `pynvml` (Python: `pip install nvidia-ml-py3`).
- Metrics: GPU utilization %, VRAM used (MB) vs 24576 MB total, power draw (watts).
- New `gpu_tracker.py` module.
- Stored as `grp='gpu'` rows in `metrics` table (machine-level; per-process GPU not feasible without NVIDIA MIG/cgroups).
- New `GpuChart.tsx` dashboard component.
- GPU data added to daily aggregates table.
- Added to /api/metrics/stream SSE payload.
- `nvidia-ml-py3` added to deployment prerequisites.

#### 6. Tagging System
**Requirement:** Allow OpenClaw, David, or anything to tag the timeline with what they're doing — category (type of work) and a text description. These tags should overlay on charts to help interpret resource logs. DavidBot must remember to use them.

**Design response:**
- New `tags` table in schema (id, ts, category, text, source, session_id).
- Categories: `conversation`, `coding`, `research`, `agent`, `heartbeat`, `qwen`, `idle`, `other`.
- New `POST /api/tags` and `GET /api/tags` endpoints.
- New `scripts/tag.sh` helper: `tag.sh <category> <text>` — validates, fires curl in background, exits 0 always.
- New `TagOverlay.tsx` + `TagLog.tsx` components.
- New `/tags` dashboard page with full tag history and manual tag creation UI.
- Tag bands + vertical lines overlaid on all time-series charts.
- **Remembering:** Addressed in README "Remembering Problem" section. DavidBot will add two lines to AGENTS.md: tag at session start and before agent spawns. This is reliable. Mid-session updates are best-effort. The design tolerates missed updates gracefully.

#### 7. Motivation Section
**Requirement:** Near the top of README, motivate why this tool exists — to help decide machine sizing (CPU speed, RAM, disk) for people's use.

**Done:** Added "Motivation" section as the first content section in README, above Goals. States the infrastructure sizing purpose clearly, including the secondary goal of understanding resource composition (gateway vs Chrome vs agents vs Qwen vs system).

### Major README Changes (Round 2)
- **New sections:** Motivation, Agent Collaboration, Tagging System, `/disk` API, `/tags` API, `/disk` and `/tags` dashboard pages
- **Revised sections:** OpenClaw Integration (renamed to "Minimal Coupling" principle), Collector (now two-loop architecture), Schema (added disk_snapshots, tags tables; updated metrics for GPU and idle heartbeat flag), File Layout (added new files), Design Decisions table (expanded to 10 decisions)
- **README was substantially rewritten** to integrate all 7 requirements coherently; previous version preserved in git history

### Status After Round 2
- [x] Repo created by David
- [x] Initial design (DavidBot + Claude Code planning session)
- [x] Adaptive polling (DavidBot)
- [x] Round 2 design review (DavidBot, this entry)
- [ ] **David reviews Round 2 plan** ← current step
- [ ] Implementation begins (Claude Code, directed by claw-monitor-builder)
- [ ] Testing
- [ ] Deployment

---

## 2026-03-06 — Adaptive Write Clarification (07:32 PST)

**Who did what:** David clarified intent. DavidBot redesigned the write gate and updated README and HISTORY. No Claude Code involvement.

### Clarification
The previous design (Round 2) still wrote an idle heartbeat row to `metrics` every 60s regardless of activity. David's intent: during 8+ hours of overnight inactivity, produce zero rows — no CPU cost from writing, no disk cost from storing zeros.

### Design Change: Strictly Activity-Gated Writes

**Old behaviour:** Write to `metrics` if activity detected OR if last write was ≥60s (idle heartbeat).
**New behaviour:** Write to `metrics` ONLY if any OpenClaw PID CPU% > 1%. Zero rows during idle. Full stop.

**Problem this creates:** Without idle heartbeat rows, the dashboard can't distinguish "nothing happened" from "the collector crashed."

**Solution:** `collector_status` — a single-row table (not an append log). The slow loop (60s) updates `last_seen` in this one row. The fast loop sets `started_at` on startup. The table never grows. Cost: one UPDATE every 60s (trivial).

Dashboard gap interpretation:
- Gap + `last_seen` falls within gap period → **grey: intentional idle**
- Gap + `last_seen` predates gap → **amber warning: collector was down**

### Schema Changes
- Removed `is_idle_heartbeat INTEGER DEFAULT 0` from `metrics` table
- Added `collector_status` table (single row, enforced by `CHECK (id = 1)`)
- `metrics` comment updated: "written ONLY when OpenClaw activity detected"

### SSE Changes
- SSE stream no longer emits events during idle (connection stays open, no data frames)
- Added `ping:` keep-alive frame every 30s to prevent proxy timeouts
- `[Live ●]` stays green during idle; goes red only on connection loss

### Activity Threshold
- 1% CPU as the write trigger (configurable in `config.py`)
- Rationale: low enough to catch brief heartbeat spikes; high enough to skip true background noise

### Status
- [x] Round 2 design complete
- [x] Write gate refined (this entry)
- [x] David approved — implementation begins 07:37 PST 2026-03-06

---

## 2026-03-06 — Full Implementation (07:45–08:00 PST)

**Who did what:** David triggered implementation. Claude Code built all phases. claw-monitor-builder managed the session.

### Implementation Summary

All 6 phases completed in a single session:

| Phase | What | Result |
|---|---|---|
| 1 | schema.sql + DB init | 7 tables, WAL mode, at ~/.openclaw/claw-monitor/metrics.db |
| 2 | claw-collector/ Python daemon | 7 modules: collector.py, db.py, pid_tracker.py, net_tracker.py, gpu_tracker.py, disk_tracker.py, config.py |
| 3 | scripts/tag.sh + register-tool.sh | Fire-and-forget shell helpers, always exit 0 |
| 4 | web/ Next.js app | 8 API routes, 11 components, 6 pages, SSE streaming, Tailscale IP guard |
| 5 | systemd units | claw-collector.service + claw-web.service installed |
| 6 | Build + deploy | npm install, npm run build, both services active |

### Build Issues Resolved

1. **next.config.ts not supported** — Next.js 14 requires .mjs, not .ts
2. **ES5 target + Set iteration** — Changed tsconfig target to es2017
3. **Token summary type inference** — Refactored to avoid spread + Record type clash
4. **Static API route caching** — Added `export const dynamic = "force-dynamic"` to registry route

### Verification

- Collector found gateway PID 35324, auto-registered 58+ processes
- Metrics flowing: CPU, memory, net, GPU data writing to DB
- All API endpoints verified: tags, tokens, registry, metrics, disk
- Both systemd services active (running)
- Dashboard accessible at http://dw-asus-linux.tail3eef35.ts.net:7432

### Status
- [x] Phase 1: Schema + DB
- [x] Phase 2: Collector
- [x] Phase 3: Scripts
- [x] Phase 4: Web app
- [x] Phase 5: systemd units
- [x] Phase 6: Build + deploy
- [x] Full stack running

---

## 2026-03-06 — First Run: Overview Page Screenshot (08:05 PST)

**Who did what:** David opened the dashboard and sent a screenshot. DavidBot archived it and noted initial observations.

Screenshot saved: `docs/screenshot-overview-first-run-2026-03-06.png`

![Overview page — first run](docs/screenshot-overview-first-run-2026-03-06.png)

### What the screenshot shows
- Dark-themed dashboard, nav: Overview / Metrics / Disk / Tokens / Processes / Tags
- Tagline "to help right-size the machine" visible under the title ✅
- Live indicator: **● Live (0s ago)** ✅
- CPU by Group chart (07:59–08:03 AM) showing heavy activity during the build — openclaw-core (blue), openclaw-browser (orange), openclaw-agent (green). The agent spike (green) correlates with Claude Code running during phases 1–4.
- GPU: ~40% utilization flat line (VRAM 1.1GB) — likely the idle GPU baseline
- Network: bursty outbound traffic during the build
- Recent Tags: `coding — claw-monitor build in progress` ✅ (tag.sh worked)
- Today's Token Usage: 1K in / 2K out, $0.03 ✅

### Obvious display bugs to fix
1. **CPU showing 27892%** — summing raw CPU% across all processes/cores without normalizing by CPU count. Should cap at 100% × number of tracked groups, or normalize per-core.
2. **Memory showing 1130.9GB of 64GB** — almost certainly summing virtual memory (VSZ) instead of RSS. Should use VmRSS from `/proc/<pid>/status`.

These are collector or display calculation bugs, not data collection bugs. Data is flowing correctly. Fixing in the next round.

---

## 2026-03-06 — First-Run Bug Fixes (08:07 PST)

**Who did what:** David spotted the bugs from the first-run screenshot. DavidBot diagnosed and fixed them directly (no Claude Code involvement — targeted frontend fix).

### Bug 1: CPU stat card showing ~27,892%

**Root cause:** `page.tsx` was accumulating `latestCpu` across every row in the 30-minute window (up to 1800 rows × N groups). A single row with cpu_pct=50 across 600 active rows = 30,000%.

**Fix:** Compute summary stats from only the most recent timestamp's rows (`latestTs`). Changed display from "%" to "cores" (cpu_pct_sum / 100), which is cleaner for a sizing tool — "OpenClaw is using 2.4 cores right now" is more actionable than a % that can legitimately exceed 100% on multi-threaded workloads.

### Bug 2: Memory showing ~1,130 GB

**Root cause:** Same accumulation bug. Memory was summed across all 1800 rows, then divided by 1024 to "convert to GB". 600 rows × 2,000 MB each = 1,200,000 MB ÷ 1024 = ~1,172 GB.

The collector was reading VmRSS correctly — the data in the DB was always right.

**Fix:** Same pattern — only sum `mem_rss_mb` from rows at `latestTs`. Label updated to "RSS (now)" for clarity.

### Files changed
- `web/src/app/page.tsx` — fixed accumulation logic, changed CPU display to "cores", updated labels
- `web/` rebuilt and `claw-web.service` restarted

---

## 2026-03-06 — Tag Backdating (08:16 PST)

**Who did what:** David requested the feature. DavidBot implemented it directly (API route + script, no Claude Code involvement).

### Feature: `ts` field on POST /api/tags

Tags can now be backdated via an optional `ts` field. Formats accepted:
- Omitted → now
- Unix timestamp (number)
- `"-10m"` / `"-30s"` / `"-2h"` — relative delta
- `"10 minutes ago"` — natural language relative
- `"2026-03-06T08:03:00"` — ISO-8601 absolute

The `resolveTs()` helper in `route.ts` handles all parsing. Returns HTTP 400 with a clear error message if the format is unrecognisable.

`tag.sh` updated: optional 5th argument is the `ts` value (passed as JSON string to the API).

All four formats smoke-tested and confirmed working.

### Files changed
- `web/src/app/api/tags/route.ts` — added `resolveTs()`, parse `ts` from body
- `scripts/tag.sh` — added optional 5th `[ts]` arg, uses `python3 -c json.dumps` for safe JSON encoding of text and ts values

---

## 2026-03-06 — Tag `recorded_at` field + backdated indicator (08:22 PST)

**Who did what:** David asked for confirmation and the indicator feature. DavidBot confirmed behaviour, implemented `recorded_at`, and added the UI indicator. No Claude Code involvement.

### Confirmation
The effective `ts` stored in the DB **is** the adjusted/backdated time — not the wall-clock submission time. Verified with live DB query: a tag posted with `ts="-15m"` is stored at 08:28, while the service received it at 08:43.

### Changes

**Schema:** Added `recorded_at INTEGER NOT NULL` to `tags` table.
- `ts` = effective timestamp (the one shown on charts; may be backdated)
- `recorded_at` = wall-clock time the POST was received (always now)
- `ts != recorded_at` (by >5s) → tag is considered backdated
- Existing rows backfilled: `recorded_at = ts` (original submission time unknown)

**API (`/api/tags`):**
- POST: always sets `recorded_at = Date.now()` server-side; `ts` = `resolveTs(rawTs)`
- GET: now returns `recorded_at` in every tag row
- Source validation updated to accept `clawbot`/`user` (new names) plus `openclaw`/`david` (legacy backcompat)

**UI (`TagLog.tsx`):**
- Backdated tags show a small superscript `↩` next to the timestamp
- Tooltip on hover shows the original submission time (`recorded_at`)
- Chart overlays (`TagOverlay.tsx`) unchanged — tags appear at `ts` with no extra annotation there

---

*Future entries appended below as the project progresses.*
