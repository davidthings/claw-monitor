# claw-monitor

> **Status: PLANNING PHASE — No code written yet. Awaiting David's review before implementation.**

A lightweight, always-on resource monitor for OpenClaw. Tracks CPU, memory, network I/O, and token consumption attributable to the OpenClaw process tree — every 10 seconds — and exposes a real-time dashboard accessible from any Tailscale-linked device.

---

## Goals

1. **Attribution**: Know exactly how much of the machine's CPU, RAM, and network is consumed by OpenClaw (gateway, headless Chrome, agents, OS utilities) vs. everything else.
2. **Token visibility**: Track LLM token usage per external tool call, registered dynamically as tools are used.
3. **Low overhead**: Collector runs at low priority (nice +10), polls every 10s, fire-and-forget.
4. **Persistent dashboard**: Available 24/7 on a fixed Tailscale-reachable port.
5. **Dynamic registration**: OpenClaw can register new PIDs/tools with a single lightweight API call — no continuous overhead.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  OpenClaw (gateway + Chrome + agents)                   │
│  ↓ fire-and-forget POST (one per new tool/PID)          │
├─────────────────────────────────────────────────────────┤
│  claw-monitor-api  (Next.js API routes, port 7432)      │
│  ├── /api/registry/process  ← PID registration          │
│  ├── /api/registry          ← list processes            │
│  ├── /api/metrics           ← query historical data     │
│  ├── /api/metrics/stream    ← SSE live feed             │
│  ├── /api/tokens            ← token event ingestion     │
│  └── /api/tokens/summary    ← aggregate token usage     │
├─────────────────────────────────────────────────────────┤
│  claw-collector  (Python daemon, nice +10, every 10s)   │
│  ├── reads /proc (CPU, mem per PID; net from /proc/net) │
│  ├── resolves PID→group via registry                    │
│  ├── verifies PID validity (detects reuse via comm)     │
│  └── writes to SQLite (WAL mode)                        │
├─────────────────────────────────────────────────────────┤
│  SQLite DB  (~/.openclaw/claw-monitor/metrics.db)       │
│  ├── metrics           (time-series: cpu/mem by group)  │
│  ├── metrics_daily     (daily aggregates, retained forever)│
│  ├── token_events      (token usage per tool call)      │
│  └── process_registry  (known PIDs + tool names)       │
├─────────────────────────────────────────────────────────┤
│  Dashboard  (Next.js + React + Radix UI + Recharts)     │
│  ├── Real-time charts (CPU, mem, network)               │
│  ├── Token usage table per tool + estimated cost        │
│  ├── Process attribution breakdown                      │
│  └── Live process registry viewer                       │
└─────────────────────────────────────────────────────────┘
```

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Collector language | Python 3 + psutil | I/O-bound, not CPU-bound. psutil handles /proc robustly. Rust saves nothing here. |
| Token cost storage | Raw counts only | Pricing changes frequently. Cost computed in dashboard via `pricing.json`. |
| Data retention | 14 days full-res, daily aggregates forever | ~35 MB for 14 days at 10s/6 groups/50 bytes. Daily is sufficient for history > 1 month. |
| Auth | Tailscale-only + IP range middleware | Tailscale = network-level auth. Middleware rejects non-Tailscale IPs as defense-in-depth. |
| Process manager | systemd (user scope) | Collector already uses systemd; consistent tooling, no extra deps, better log rotation. |
| Live updates | SSE (Server-Sent Events) | One-directional push, native to Next.js, 10s interval, auto-reconnect built into EventSource. |
| Network I/O | Machine-level only | Per-PID net accounting requires libpcap or cgroups. Machine-level from /proc/net/dev is sufficient. |
| DB concurrency | WAL mode | Both Python collector and Next.js API open with `PRAGMA journal_mode=WAL`. No SQLITE_BUSY errors. |

---

## Components

### 1. `claw-collector/` — Python daemon

- **Language:** Python 3 + psutil + sqlite3 (stdlib)
- **Poll interval:** 10 seconds
- **Priority:** `nice +10` (SCHED_OTHER, low priority)
- **Process manager:** `claw-collector.service` (systemd user scope)

#### Collector Core Loop

```
On startup:
  1. Open SQLite DB (WAL mode)
  2. Create tables if not exist
  3. Bootstrap: auto-discover openclaw-gateway PID via /proc/*/cmdline scan
     Walk child tree via /proc/<pid>/children to auto-register all children
  4. Load process_registry into memory

Every 10s:
  1. Reload process_registry (small SELECT, catches new API registrations)
  2. For each registered PID:
     a. Check /proc/<pid> exists → if not, mark unregistered in DB
     b. Read /proc/<pid>/comm → if doesn't match registered name, mark unregistered (PID reuse!)
     c. Read /proc/<pid>/stat → get utime+stime (cumulative CPU ticks)
     d. Read /proc/<pid>/status → get VmRSS (memory)
     e. Compute CPU% = (ticks_now - ticks_prev) / (elapsed_s * cpu_count)
        (First sample after PID registration has no CPU data — emit NULL for that tick)
  3. Aggregate per group: sum CPU%, sum RSS
  4. Read /proc/net/dev → compute delta for net in/out bytes
  5. INSERT one row per group into metrics (no net columns)
  6. INSERT one row with grp='machine' containing net_in_kb, net_out_kb
  7. Daily (first tick after midnight):
     - INSERT aggregated rows into metrics_daily
     - DELETE FROM metrics WHERE ts < (now - 14 days)

On SIGTERM: clean shutdown, close DB
```

#### PID Auto-Grouping Rules

| Condition | Group |
|---|---|
| Process is `openclaw-gateway` | `openclaw-core` |
| Direct child of gateway, `chrome`/`chromium` in cmdline | `openclaw-browser` |
| Direct child of gateway, other | `openclaw-core` |
| Grandchild+ of gateway | `openclaw-agent` |
| Manually registered with explicit group | (as specified) |

#### Known Limitations

- **PID churn**: Processes that live and die within a single 10s window are missed entirely. Acceptable — short-lived processes contribute minimal resource usage. Token tracking is unaffected (handled via API).
- **No per-PID network I/O**: Machine-level net only. Feasible improvement in v2 (cgroups or eBPF).
- **First sample after registration**: CPU% is NULL because delta calculation requires two readings.

---

### 2. `web/` — Next.js app (TypeScript)

- **Framework:** Next.js 14 (App Router), React, Radix UI Themes, Recharts
- **Port:** 7432 (permanent, bound to 0.0.0.0)
- **Process manager:** `claw-web.service` (systemd user scope)
- **DB access:** `better-sqlite3` (synchronous, WAL mode)

#### Middleware: Tailscale IP Guard

All routes are protected by a middleware that rejects requests not originating from:
- `127.0.0.1` (localhost)
- `100.64.0.0/10` (Tailscale CGNAT range)

Returns `403 Forbidden` otherwise. This is defense-in-depth alongside Tailscale network auth — not a full auth system.

#### Pricing Config

`web/src/lib/pricing.json` — maps model IDs to per-token costs in USD. Updated manually when pricing changes.

```json
{
  "claude-sonnet-4-6": { "input_per_mtok": 3.00, "output_per_mtok": 15.00 },
  "claude-haiku-4-5":  { "input_per_mtok": 0.25, "output_per_mtok": 1.25 },
  "gpt-4o":            { "input_per_mtok": 5.00, "output_per_mtok": 15.00 },
  "gpt-4o-mini":       { "input_per_mtok": 0.15, "output_per_mtok": 0.60 }
}
```

---

### 3. OpenClaw Integration

OpenClaw fires a single `curl` in the background when:
- A new agent/tool PID is spawned → `POST /api/registry/process`
- A tool call returns token usage → `POST /api/tokens`

**Zero coupling:** If claw-monitor is down, the curl fails silently. OpenClaw is unaffected. The collector will still auto-discover OpenClaw PIDs on its next scan.

---

## API Specification

### `POST /api/registry/process`
Register a PID for monitoring.

**Request:**
```json
{
  "pid": 12345,
  "name": "chrome",
  "group": "openclaw-browser",
  "description": "Headless Chrome for web scraping"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `pid` | integer | ✅ | OS process ID (positive integer) |
| `name` | string | ✅ | Should match `/proc/<pid>/comm` (used for PID reuse detection) |
| `group` | string | ✅ | One of: `openclaw-core`, `openclaw-browser`, `openclaw-agent`, `system` |
| `description` | string | — | Human-readable note |

**Response 201:**
```json
{ "ok": true, "registered": 1709712000 }
```

**Response 400:** PID not a positive integer, or group not in allowed set.

---

### `POST /api/tokens`
Log a token usage event.

**Request:**
```json
{
  "tool": "web-search",
  "model": "claude-sonnet-4-6",
  "tokens_in": 1500,
  "tokens_out": 3200,
  "session_id": "agent-7a3b"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `tool` | string | ✅ | Tool/function name |
| `model` | string | ✅ | Model identifier (used for cost computation) |
| `tokens_in` | integer | ✅ | Input/prompt token count |
| `tokens_out` | integer | ✅ | Output/completion token count |
| `session_id` | string | — | Correlates events to an agent session |

**Response 201:**
```json
{ "ok": true, "id": 42 }
```

---

### `GET /api/metrics`
Query time-series resource data.

**Query params:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `from` | unix timestamp | required | Start of range |
| `to` | unix timestamp | now | End of range |
| `group` | string | all | Filter by group name |
| `resolution` | string | `auto` | `raw`, `hourly`, `daily`, or `auto` |

Auto resolution: `< 6h` → raw, `6h–3d` → hourly, `> 3d` → daily.

For hourly/daily within 14-day window: aggregated on the fly. For older data: reads from `metrics_daily`.

**Response 200:**
```json
{
  "data": [
    {
      "ts": 1709712000,
      "group": "openclaw-core",
      "cpu_pct": 34.2,
      "mem_rss_mb": 512.3
    },
    {
      "ts": 1709712000,
      "group": "machine",
      "net_in_kb": 120.5,
      "net_out_kb": 45.2
    }
  ],
  "count": 2,
  "resolution": "raw"
}
```

---

### `GET /api/metrics/stream`
SSE live feed. Emits one event per collector tick (~10s).

**Response headers:** `Content-Type: text/event-stream`

**Event format:**
```
data: {"ts":1709712000,"groups":{"openclaw-core":{"cpu_pct":34.2,"mem_rss_mb":512.3},"openclaw-browser":{"cpu_pct":12.1,"mem_rss_mb":1024.0},"openclaw-agent":{"cpu_pct":5.0,"mem_rss_mb":128.0}},"net":{"in_kb":120.5,"out_kb":45.2}}

```

Clients reconnect automatically via `EventSource`. The `[Live ●]` indicator in the dashboard turns red if the connection drops.

---

### `GET /api/registry`
List registered processes.

**Query params:** `active=true` (optional) — return only where `unregistered IS NULL`.

**Response 200:**
```json
{
  "processes": [
    {
      "id": 1,
      "pid": 12345,
      "name": "chrome",
      "group": "openclaw-browser",
      "description": "Headless Chrome",
      "registered": 1709712000,
      "unregistered": null,
      "alive": true
    }
  ]
}
```

The `alive` field is computed live by checking `/proc/<pid>` existence at query time.

---

### `GET /api/tokens/summary`
Aggregate token usage.

**Query params:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `from` | unix timestamp | 24h ago | Start of range |
| `to` | unix timestamp | now | End of range |
| `group_by` | string | `tool` | `tool`, `model`, or `session_id` |

**Response 200:**
```json
{
  "summary": [
    {
      "tool": "web-search",
      "total_in": 45000,
      "total_out": 120000,
      "call_count": 23,
      "models": ["claude-sonnet-4-6"],
      "est_cost_usd": 6.20
    }
  ],
  "totals": {
    "tokens_in": 45000,
    "tokens_out": 120000,
    "calls": 23,
    "est_cost_usd": 6.20
  }
}
```

Cost is computed server-side using `pricing.json` at query time.

---

## Database Schema (SQLite)

```sql
PRAGMA journal_mode=WAL;  -- Must be set by both collector and web app

-- Time-series resource metrics (per group, per tick)
-- Network I/O stored in rows where grp = 'machine'
CREATE TABLE metrics (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         INTEGER NOT NULL,  -- unix timestamp
  grp        TEXT NOT NULL,     -- 'openclaw-core' | 'openclaw-browser' | 'openclaw-agent' | 'system' | 'machine'
  cpu_pct    REAL,              -- NULL on first sample after PID registration
  mem_rss_mb REAL,
  net_in_kb  REAL,              -- Only set when grp = 'machine'
  net_out_kb REAL               -- Only set when grp = 'machine'
);
CREATE INDEX idx_metrics_ts ON metrics(ts);
CREATE INDEX idx_metrics_grp_ts ON metrics(grp, ts);

-- Daily aggregates (retained forever)
CREATE TABLE metrics_daily (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  date           TEXT NOT NULL,  -- 'YYYY-MM-DD'
  grp            TEXT NOT NULL,
  avg_cpu_pct    REAL,
  max_cpu_pct    REAL,
  avg_mem_rss_mb REAL,
  max_mem_rss_mb REAL,
  sum_net_in_kb  REAL,
  sum_net_out_kb REAL,
  UNIQUE(date, grp)
);

-- Registered processes
-- NOTE: id is the primary key (NOT pid) to handle Linux PID reuse correctly
CREATE TABLE process_registry (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  pid          INTEGER NOT NULL,
  name         TEXT NOT NULL,    -- expected /proc/<pid>/comm value
  grp          TEXT NOT NULL,
  description  TEXT,
  registered   INTEGER NOT NULL,
  unregistered INTEGER           -- set when PID dies or comm mismatch detected
);
CREATE INDEX idx_registry_pid ON process_registry(pid);

-- Token usage events
CREATE TABLE token_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         INTEGER NOT NULL,
  tool       TEXT NOT NULL,
  model      TEXT NOT NULL,    -- required for cost computation
  tokens_in  INTEGER,
  tokens_out INTEGER,
  session_id TEXT              -- optional, correlates events to agent sessions
);
CREATE INDEX idx_token_events_ts ON token_events(ts);
CREATE INDEX idx_token_events_tool ON token_events(tool);
```

### Schema Design Notes

- **`process_registry.id` is the PK**, not `pid`. Linux recycles PIDs — using pid as PK causes collision when a new process reuses a dead PID. The collector verifies `/proc/<pid>/comm` matches `name` before trusting a PID.
- **`cost_usd` is not stored**. Pricing changes; compute cost from raw counts + `pricing.json` at query time.
- **`model` is NOT NULL** in `token_events`. Required for cost computation to work.
- **`session_id`** in `token_events` enables future per-session token attribution.
- **Network I/O** is stored in a dedicated `grp='machine'` row — not replicated across all group rows.

---

## File Layout

```
~/work/claw-monitor/
├── README.md                     ← this file (design document)
├── HISTORY.md                    ← decision log / change log
├── schema.sql                    ← SQLite schema (run once to initialize DB)
│
├── claw-collector/
│   ├── collector.py              ← main daemon entry point, core 10s loop
│   ├── db.py                     ← SQLite helpers (open with WAL, insert, retention cleanup)
│   ├── pid_tracker.py            ← /proc-based PID walker, comm verification, auto-grouping
│   ├── net_tracker.py            ← /proc/net/dev reader, delta computation
│   └── claw-collector.service   ← systemd user unit file
│
├── web/
│   ├── package.json
│   ├── next.config.ts            ← port: 7432, standalone output
│   ├── tsconfig.json
│   ├── claw-web.service          ← systemd user unit file
│   └── src/
│       ├── middleware.ts         ← Tailscale IP guard (100.64.0.0/10 + 127.0.0.1)
│       ├── lib/
│       │   ├── db.ts             ← better-sqlite3 singleton (WAL mode)
│       │   ├── pricing.json      ← model → {input_per_mtok, output_per_mtok}
│       │   └── cost.ts           ← cost computation helper
│       ├── app/
│       │   ├── layout.tsx        ← Radix UI Theme wrapper, nav sidebar
│       │   ├── page.tsx          ← / Live Overview
│       │   ├── metrics/
│       │   │   └── page.tsx      ← /metrics Time-Series Explorer
│       │   ├── tokens/
│       │   │   └── page.tsx      ← /tokens Token Usage Breakdown
│       │   ├── processes/
│       │   │   └── page.tsx      ← /processes Process Registry
│       │   └── api/
│       │       ├── registry/
│       │       │   └── process/
│       │       │       └── route.ts  ← POST /api/registry/process
│       │       ├── registry/
│       │       │   └── route.ts      ← GET /api/registry
│       │       ├── metrics/
│       │       │   ├── route.ts      ← GET /api/metrics
│       │       │   └── stream/
│       │       │       └── route.ts  ← GET /api/metrics/stream (SSE)
│       │       └── tokens/
│       │           ├── route.ts      ← POST /api/tokens
│       │           └── summary/
│       │               └── route.ts  ← GET /api/tokens/summary
│       └── components/
│           ├── MetricSparkline.tsx   ← small Recharts LineChart
│           ├── CpuAreaChart.tsx      ← stacked area chart (Recharts)
│           ├── TokenTable.tsx        ← Radix UI Table, sortable
│           ├── ProcessTable.tsx      ← Radix UI Table with alive/dead badge
│           ├── LiveIndicator.tsx     ← SSE connection status dot
│           └── CostBadge.tsx         ← formats est. USD cost
│
└── scripts/
    └── register-tool.sh          ← OpenClaw integration helper
```

---

## OpenClaw → Monitor Integration Protocol

### Registering a New Process

When OpenClaw spawns a new agent/tool process:

```bash
# Fire-and-forget PID registration (non-blocking)
curl -sf \
  -X POST http://localhost:7432/api/registry/process \
  -H 'Content-Type: application/json' \
  -d "{
    \"pid\": ${NEW_PID},
    \"name\": \"$(cat /proc/${NEW_PID}/comm 2>/dev/null || echo unknown)\",
    \"group\": \"openclaw-agent\",
    \"description\": \"${TOOL_NAME}\"
  }" &
```

- **Timing:** Called once immediately after process spawn
- **`&`**: Non-blocking — OpenClaw does not wait for a response
- **`-sf`**: Silent + fail fast — no output, no retries, no hanging
- **name field**: Should match `/proc/<pid>/comm` — collector uses this to detect PID reuse

### Logging Token Usage

After each LLM tool call completes:

```bash
# Fire-and-forget token event (non-blocking)
curl -sf \
  -X POST http://localhost:7432/api/tokens \
  -H 'Content-Type: application/json' \
  -d "{
    \"tool\": \"${TOOL_NAME}\",
    \"model\": \"${MODEL_ID}\",
    \"tokens_in\": ${TOKENS_IN},
    \"tokens_out\": ${TOKENS_OUT},
    \"session_id\": \"${SESSION_ID}\"
  }" &
```

- **Timing:** Called once per tool call completion, after usage metadata is available
- **Not called** on tool call failure (no tokens consumed)
- **session_id:** Identifies the agent session (e.g., `agent:main:signal:direct:+15303386428`)

### Helper Script: `scripts/register-tool.sh`

```
Usage:
  register-tool.sh process <pid> <name> <group> [description]
  register-tool.sh tokens <tool> <model> <tokens_in> <tokens_out> [session_id]

Examples:
  register-tool.sh process 12345 chrome openclaw-browser "Headless Chrome"
  register-tool.sh tokens web-search claude-sonnet-4-6 1500 3200 agent-7a3b
```

The script validates arguments and always exits 0, regardless of whether claw-monitor is reachable. It constructs the JSON and fires the appropriate curl command.

### Failure Modes

| Scenario | Impact |
|---|---|
| Monitor not running when process registered | curl fails silently. Collector auto-discovers OpenClaw PIDs via /proc scan on its next bootstrap. |
| Monitor not running when tokens logged | That tool call's token count is permanently missing from totals. Acceptable. |
| PID dies before registration is processed | API inserts the row; collector marks it `unregistered` on its next tick when `/proc/<pid>` is gone. |
| PID reused by unrelated process | Collector detects `/proc/<pid>/comm` mismatch, marks old row `unregistered`, ignores new process. |
| SQLite write contention | WAL mode serializes concurrent writes with ~millisecond waits. No data loss. |

---

## Dashboard Wireframes

### `/` — Live Overview

```
┌────────────────────────────────────────────────────────────┐
│  🦞 CLAW MONITOR                [Live ●] [Last: 2s ago]   │
├───────────────┬─────────────────┬──────────────────────────┤
│  CPU           │  Memory          │  Network                │
│  ████████░ 62% │  1.8 / 64 GB    │  ↓ 1.2 MB/s ↑ 340KB/s │
│  [sparkline]   │  [sparkline]     │  [sparkline]           │
├───────────────┴─────────────────┴──────────────────────────┤
│  CPU by Group — Last 30 minutes (stacked area chart)       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ██████ openclaw-core  ████ browser  ██ agent  █ sys │  │
│  └──────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────┤
│  Memory by Group — Last 30 minutes                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ████████████ openclaw-browser  ██████ core  ██ agent│  │
│  └──────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────┤
│  Today's Token Usage                                        │
│  1.2M in / 3.4M out  │  Est. cost: $4.20  │  89 calls     │
│  Top tool: web-search (42 calls, $2.10)                    │
│                                      [→ Full breakdown]    │
├────────────────────────────────────────────────────────────┤
│  Active Processes: 12 tracked                              │
│  openclaw-core: 3  │  browser: 4  │  agent: 5             │
│                                      [→ View registry]    │
└────────────────────────────────────────────────────────────┘
```

- Sparklines: last 30 minutes (180 data points from SSE history)
- All data auto-refreshes via SSE (~10s)
- `[Live ●]` turns red if SSE disconnects; reconnects automatically
- Cost computed client-side from raw token counts + pricing.json

---

### `/metrics` — Time-Series Explorer

```
┌────────────────────────────────────────────────────────────┐
│  Metrics Explorer                                           │
│  [📅 2026-02-28] → [📅 2026-03-06]  [Group: All ▼]       │
│  [Resolution: Auto ▼]   [Refresh: Paused | Live]          │
├────────────────────────────────────────────────────────────┤
│  CPU % — Stacked Area Chart                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │100%│                                                  │  │
│  │    │  ▓▓▓░░░░░░░▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  │
│  │ 50%│  ████░░░░░░███████░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  │
│  │  0%│──────────────────────────────────────────────── │  │
│  └──────────────────────────────────────────────────────┘  │
│  [Brush: drag to zoom into a time range]                   │
├────────────────────────────────────────────────────────────┤
│  Memory RSS — Stacked Area Chart                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 4GB│  ████████████████████████████████████████████   │  │
│  │ 2GB│  ████████████████████████████████████████████   │  │
│  │  0 │──────────────────────────────────────────────── │  │
│  └──────────────────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────┤
│  Network I/O — Machine Level (Line Chart)                   │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ ↓ in  ━━━━╱╲━━━━╱╲╱╲━━━━━━━━━━━━╱╲╱╲╱╲━━━━━━━━━━  │  │
│  │ ↑ out ────╱╲────╱╲╱╲────────────╱╲╱╲╱╲────────────  │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

- Resolution auto-selects based on date range (raw/hourly/daily)
- Hover tooltip shows exact value at any timestamp
- Brush selection to zoom; double-click to reset
- Group filter hides/shows individual groups in stacked charts

---

### `/tokens` — Token Usage Breakdown

```
┌────────────────────────────────────────────────────────────┐
│  Token Usage         [Today | 7d | 30d | Custom 📅]        │
├────────────────────────────────────────────────────────────┤
│  5.2M in  /  12.8M out  /  Est. cost: $18.40  /  312 calls│
├────────────────────────────────────────────────────────────┤
│  By Tool  (sortable table)                                  │
│  ┌────────────┬───────┬─────────┬──────────┬─────────────┐ │
│  │ Tool       │ Calls │ Tok In  │ Tok Out  │  Est. Cost  │ │
│  ├────────────┼───────┼─────────┼──────────┼─────────────┤ │
│  │ web-search │  42   │  1.2M   │   3.4M   │    $6.20    │ │
│  │ exec       │  31   │  0.9M   │   2.8M   │    $5.10    │ │
│  │ read       │  28   │  0.6M   │   1.8M   │    $3.20    │ │
│  │ image-gen  │  11   │  0.3M   │   0.8M   │    $1.90    │ │
│  └────────────┴───────┴─────────┴──────────┴─────────────┘ │
├────────────────────────────────────────────────────────────┤
│  By Model (donut chart + legend)                            │
│  ◉ claude-sonnet-4-6  72%  $13.20                          │
│  ◎ claude-haiku-4-5   18%   $1.80                          │
│  ◎ gpt-4o-mini        10%   $3.40                          │
├────────────────────────────────────────────────────────────┤
│  Token Usage Over Time (daily bar chart)                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ████░ ████░ ██░░ ████░ ████░ ████░ ████░           │  │
│  │  M 2/28 3/1  3/2  3/3   3/4   3/5   3/6            │  │
│  │  ░=tokens_in  █=tokens_out                          │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

- All costs computed client-side from raw counts + pricing.json
- Table columns sortable by any field
- "Pricing as of YYYY-MM-DD" note shown under summary

---

### `/processes` — Process Registry

```
┌────────────────────────────────────────────────────────────┐
│  Process Registry              [Show: Active ▼]  [Refresh] │
├────────────────────────────────────────────────────────────┤
│  12 tracked  │  10 alive  │  2 recently dead               │
├────────────────────────────────────────────────────────────┤
│  ┌──────┬─────────┬─────────────────┬────────┬──────────┐  │
│  │ PID  │ Name    │ Group           │ Status │ Since    │  │
│  ├──────┼─────────┼─────────────────┼────────┼──────────┤  │
│  │12345 │ chrome  │ openclaw-browser│ ● live │ 3h ago   │  │
│  │12346 │ node    │ openclaw-core   │ ● live │ 3h ago   │  │
│  │12400 │ python3 │ openclaw-agent  │ ● live │ 12m ago  │  │
│  │12101 │ curl    │ openclaw-agent  │ ○ dead │ 45m ago  │  │
│  └──────┴─────────┴─────────────────┴────────┴──────────┘  │
├────────────────────────────────────────────────────────────┤
│  Group Breakdown (donut chart)                              │
│  ◉ openclaw-browser  4    ◎ openclaw-core  3               │
│  ◎ openclaw-agent    5    ◎ dead           2               │
└────────────────────────────────────────────────────────────┘
```

- `● live` / `○ dead` computed by API (checks `/proc/<pid>` at query time)
- Dead processes shown with muted style; auto-hidden in "Active" view
- Clicking a row shows description tooltip

---

## Startup / Deployment Steps

### Prerequisites

- Python 3.10+
- Node.js 20+
- SQLite 3.35+ (for WAL mode)
- systemd (user scope)
- Tailscale active

### Step-by-Step

```bash
# 1. Create database directory
mkdir -p ~/.openclaw/claw-monitor/

# 2. Initialize SQLite DB
sqlite3 ~/.openclaw/claw-monitor/metrics.db < schema.sql
# schema.sql sets PRAGMA journal_mode=WAL and creates all tables

# 3. Install Python collector dependencies
cd ~/work/claw-monitor/claw-collector
pip install --user psutil
# sqlite3 is Python stdlib — no extra install needed

# 4. Install Node.js web dependencies
cd ~/work/claw-monitor/web
npm install

# 5. Build Next.js for production
npm run build
# Output: web/.next/ (standalone mode)

# 6. Install systemd user units
cp ~/work/claw-monitor/claw-collector/claw-collector.service ~/.config/systemd/user/
cp ~/work/claw-monitor/web/claw-web.service ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now claw-collector.service
systemctl --user enable --now claw-web.service

# 7. Enable user lingering (so services run without active login)
loginctl enable-linger $USER

# 8. Verify services
systemctl --user status claw-collector claw-web

# 9. Verify API
curl -s http://localhost:7432/api/registry | jq .

# 10. Verify Tailscale access (from this machine)
curl -s http://dw-asus-linux.tail3eef35.ts.net:7432/api/registry | jq .
# Then open http://dw-asus-linux.tail3eef35.ts.net:7432 in a browser from any Tailscale peer
```

### systemd Unit Structure (both services)

Both units:
- Run as `[Service] Type=simple`
- Set `Restart=always`, `RestartSec=5`
- Set `Nice=10` for the collector (low priority)
- Use `WantedBy=default.target`
- Log to journald (use `journalctl --user -u claw-collector -f` to tail)
- **No dependency ordering needed** — services are independent; they share SQLite but don't need each other to be running.

### Day-to-Day Operations

```bash
# Tail collector logs
journalctl --user -u claw-collector -f

# Tail web logs
journalctl --user -u claw-web -f

# Restart after code changes
systemctl --user restart claw-collector
systemctl --user restart claw-web

# Check both at once
systemctl --user status claw-*
```

---

## Port & Networking

| Service | Port | Bind | Notes |
|---|---|---|---|
| Next.js web | 7432 | 0.0.0.0 | Accessible on all interfaces |
| Tailscale | — | — | Exposes 7432 to all tailnet peers |

Access from any Tailscale device: `http://dw-asus-linux.tail3eef35.ts.net:7432`

**Not exposed to public internet** — Tailscale acts as the auth boundary. Middleware adds IP range validation as defense-in-depth.

---

## Open Questions (Resolved)

| # | Question | Decision |
|---|---|---|
| 1 | Python vs Rust for collector? | **Python** — I/O-bound, not CPU-bound. psutil handles /proc robustly. Rust saves nothing measurable here. |
| 2 | Token cost tracking: raw counts or compute USD? | **Raw counts only** — compute USD in dashboard via `pricing.json`. Pricing changes too often to bake into DB. |
| 3 | Data retention policy? | **14 days full-res, daily aggregates forever** — ~35 MB for 14 days. Daily sufficient for historical trends. |
| 4 | Auth on port 7432? | **Tailscale-only + IP range middleware** — 5-line middleware rejects non-Tailscale IPs as defense-in-depth. |
| 5 | PM2 vs systemd? | **systemd (user scope)** — consistent with collector, no extra deps, better log rotation and status tooling. |
| 6 | WebSocket vs SSE? | **SSE** — unidirectional data flow, native to Next.js, auto-reconnect built-in, 10s interval means no latency concerns. |

---

## Not In Scope (v1)

- GPU usage monitoring (RTX 3090 available — v2 candidate)
- Per-PID network I/O (requires libpcap or eBPF — v2)
- Alert/notification system (e.g., "CPU > 90% for 5 min")
- Multi-machine monitoring
- Per-request latency tracking
- Authentication beyond Tailscale + IP guard
