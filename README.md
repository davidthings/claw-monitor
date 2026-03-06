# claw-monitor

> **Status: PLANNING PHASE — No code written yet. Awaiting David's review before implementation.**

---

## Motivation

David runs OpenClaw on a Linux server (RTX 3090, 64 GB RAM). The goal of this tool is to answer a practical question:

> **How big does the machine need to be — CPU speed, RAM, disk — to support people's use of OpenClaw?**

Right now the system is oversized by design (a beefy workstation repurposed as a server). claw-monitor provides the data to right-size future hardware: What's the peak CPU? How much RAM does a busy conversation actually need? How fast does storage grow? Does GPU matter for OpenClaw itself or only for local LLMs? Over time, these measurements across real usage patterns give a factual basis for infrastructure decisions instead of guesswork.

Secondary goal: understanding the *composition* of resource use — what fraction is the gateway itself, what fraction is headless Chrome, what fraction is spawned agents, what fraction is the local LLM, and what fraction is unrelated system activity.

---

## Agent Collaboration

Three agents built and maintain this project:

| Agent | Role | Scope |
|---|---|---|
| **DavidBot** (OpenClaw main session) | Orchestrator & integration owner | Receives David's requirements; writes/updates design docs; incorporates feedback; owns the OpenClaw-side integration (tagging calls, token reporting); directs the builder subagent |
| **claw-monitor-builder** (OpenClaw subagent) | Project manager | Spawned by DavidBot; manages Claude Code; translates design into implementation tasks; reviews Claude Code output; maintains README.md and HISTORY.md during build phase |
| **Claude Code** | Implementation agent | Runs in `~/work/claw-monitor/`; writes all application code; follows design spec; PLANNING MODE ONLY until David approves |

**Decision authority:** DavidBot writes the design docs and has final say on what goes in. Claude Code can surface implementation concerns (and already resolved several architectural bugs during planning). claw-monitor-builder routes those concerns back to DavidBot and David.

**Attribution convention in HISTORY.md:** Each significant decision notes which agent drove it, at a high level (e.g., "Claude Code identified PID reuse bug; resolved by DavidBot in schema").

---

## Goals

1. **Right-size data** for infrastructure decisions: CPU, RAM, disk, network requirements for OpenClaw under real usage
2. **Attribution**: know what fraction of machine resources is OpenClaw (gateway, browser, agents) vs. local LLM (Qwen) vs. unrelated system activity
3. **Token visibility**: track LLM token consumption per tool type for cost analysis
4. **Tagging**: let OpenClaw and David annotate the timeline with work-type context (so raw numbers can be correlated with what was happening)
5. **Low overhead**: collector doesn't noticeably compete with OpenClaw or Qwen
6. **Persistent dashboard**: available 24/7 on a fixed Tailscale-reachable port from any device

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  OpenClaw (gateway + Chrome + agents)                       │
│  ↓ tag POST at session start / work-type change (trivial)   │
│  ↓ token POST after each LLM tool call (fire-and-forget)    │
├─────────────────────────────────────────────────────────────┤
│  claw-monitor-api  (Next.js API routes, port 7432)          │
│  ├── /api/tags           ← work-type tag ingestion          │
│  ├── /api/tokens         ← token event ingestion            │
│  ├── /api/registry       ← (optional) explicit PID hints    │
│  ├── /api/metrics        ← query historical data            │
│  ├── /api/metrics/stream ← SSE live feed                    │
│  └── /api/tokens/summary ← aggregate token usage           │
├─────────────────────────────────────────────────────────────┤
│  claw-collector  (Python daemon, nice +10)                  │
│  ├── FAST LOOP (1s): CPU, mem, net, GPU                     │
│  │   └── writes to DB only on activity OR every 60s (idle)  │
│  ├── SLOW LOOP (60s): disk space per directory              │
│  ├── resolves PID→group automatically via /proc scan        │
│  ├── GPU via pynvml (RTX 3090)                              │
│  └── SQLite WAL mode                                        │
├─────────────────────────────────────────────────────────────┤
│  SQLite DB  (~/.openclaw/claw-monitor/metrics.db)           │
│  ├── metrics         (cpu/mem/net/gpu — written on activity) │
│  ├── metrics_daily   (daily aggregates, retained forever)   │
│  ├── disk_snapshots  (per-directory sizes, every 60s)       │
│  ├── token_events    (per-tool-call token usage)            │
│  ├── tags            (work-type annotations)                │
│  └── process_registry (known PIDs + groups)                 │
├─────────────────────────────────────────────────────────────┤
│  Dashboard  (Next.js + React + Radix UI + Recharts)         │
│  ├── Real-time charts (CPU/mem/GPU/net, with tag overlays)  │
│  ├── Disk usage timeline + breakdown                        │
│  ├── Token usage by tool/model/session                      │
│  └── Process registry viewer                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Collector language | Python 3 + psutil + pynvml | I/O-bound; psutil handles /proc robustly; pynvml is the standard NVIDIA Python binding; <300 lines total |
| Token cost storage | Raw counts only | Pricing changes frequently; compute USD in dashboard via `pricing.json` |
| Data retention | 14 days full-res, daily aggregates forever | ~50 MB for 14 days with 1s-resolution writes on active periods; daily sufficient for long-term trends |
| Auth | Tailscale + IP range middleware | Tailscale = network-level auth; middleware rejects non-Tailscale IPs as defense-in-depth |
| Process manager | systemd (user scope) | Consistent tooling, no extra deps, native log rotation |
| Live updates | SSE (Server-Sent Events) | One-directional push, native to Next.js, auto-reconnect built in |
| Network I/O | Machine-level only | Per-PID net requires libpcap/cgroups; machine-level from `/proc/net/dev` is sufficient for sizing questions |
| GPU | Machine-level via pynvml | Can't attribute GPU per-process without cgroups/MIG; machine-level shows Qwen vs idle clearly |
| DB concurrency | WAL mode | Both Python and Node.js set `PRAGMA journal_mode=WAL`; prevents `SQLITE_BUSY` errors |
| Sweep vs write | Strictly activity-gated | 1s sweep always; write to `metrics` ONLY when OpenClaw CPU% > 1%; zero rows overnight; `collector_status` updated every 60s so dashboard can distinguish idle from crash |
| Disk stats | Slow loop (60s) | Directory scanning with `os.walk()` is expensive; 60s is fine for storage growth analysis |
| OpenClaw coupling | Minimal | Collector autodiscovers all PIDs from /proc; OpenClaw only provides tags (work type) and token counts |

---

## Components

### 1. `claw-collector/` — Python daemon

- **Language:** Python 3 + psutil + pynvml + sqlite3 (stdlib)
- **Priority:** `nice +10` (SCHED_OTHER — low priority)
- **Process manager:** `claw-collector.service` (systemd user scope)

#### Two-Loop Architecture

The collector runs two independent loops:

**Fast loop (1s sweep):** Reads CPU%, mem (RSS), net I/O delta, GPU utilization, GPU VRAM. Holds results in memory. Writes to the `metrics` table **only when activity is detected** — never during idle periods. This means overnight silence produces zero rows, not thousands of zero-value rows.

**Slow loop (60s):** Two tasks:
1. Scans disk directories with `os.walk()`. Writes one `disk_snapshots` row per 60s regardless of activity — disk growth is always tracked.
2. Updates `collector_status.last_seen` — a single-row table (not appended, just updated). This is how the dashboard knows the collector is alive even when no metrics are being written.

#### Activity Detection: When to Write to `metrics`

| Condition | Action |
|---|---|
| Any OpenClaw PID CPU% > 1% | Write fast-loop sample to DB immediately |
| All OpenClaw PIDs CPU% ≤ 1% | Skip write — no row produced |

That's the entire rule. The `metrics` table contains **only rows where something was happening.** Gaps in the timeline are intentional.

#### Distinguishing Idle from Collector-Down

Without idle heartbeat rows, the dashboard cannot tell the difference between "nothing happened" and "the collector crashed" purely from `metrics` gaps. This is resolved by `collector_status`:

```sql
-- Single-row table. Always UPDATE, never INSERT after init.
CREATE TABLE collector_status (
  id         INTEGER PRIMARY KEY CHECK (id = 1),  -- enforces single row
  last_seen  INTEGER NOT NULL,                     -- unix timestamp, updated every 5 min
  started_at INTEGER NOT NULL                      -- timestamp of last collector startup
);
```

The collector updates `last_seen` every 5 minutes regardless of activity. The dashboard interprets timeline gaps as:

| Gap duration | `last_seen` during gap? | Interpretation |
|---|---|---|
| Any length | Yes (last_seen falls within gap) | ✅ Intentional idle — collector was running, nothing to report |
| Any length | No (last_seen before gap starts) | ⚠️ Collector was down — show warning banner |

Dashboard shows idle gaps as a muted grey region. Collector-down gaps show an amber warning. No ambiguity, and zero wasted disk rows overnight.

#### Fast Loop — Core Logic

```
On startup:
  1. Open SQLite DB (WAL mode), create tables if not exist
  2. Bootstrap: scan /proc/*/cmdline to find openclaw-gateway PID
     Walk child tree to discover all children; auto-assign groups
  3. Init pynvml; open GPU handle for device 0 (RTX 3090)
  4. INSERT OR REPLACE INTO collector_status (id, last_seen, started_at) VALUES (1, now, now)
  5. last_write_ts = 0

Every 1 second:
  1. Reload process_registry from DB (catch new API registrations)
  2. For each registered PID:
     a. Check /proc/<pid> exists → if not, mark unregistered
     b. Read /proc/<pid>/comm → verify matches registered name (PID reuse detection)
     c. Read /proc/<pid>/stat → compute CPU% (delta from previous tick)
     d. Read /proc/<pid>/status → get VmRSS (memory)
  3. Aggregate per group: sum CPU%, sum RSS
  4. Read /proc/net/dev → compute net in/out delta since last tick
  5. Read GPU: gpu_util_pct, vram_used_mb, power_w via pynvml
  6. Determine whether to write:
     active = any_openclaw_pct > 1.0
     If active:
       INSERT rows into metrics (one per group, plus 'net' row, plus 'gpu' row)
       Set sample_interval_s = (now - last_write_ts)
       last_write_ts = now
     Else:
       No write — fast loop goes back to sleep

Every 60 seconds (slow loop, runs concurrently):
  1. Scan configured directories with os.walk(); record total size in bytes
  2. INSERT one row per directory into disk_snapshots
  3. UPDATE collector_status SET last_seen = now WHERE id = 1
  4. Daily: INSERT into metrics_daily; DELETE old rows from metrics (>14 days)

On SIGTERM: clean shutdown, close GPU handle, close DB
```

#### PID Auto-Grouping Rules

| Condition | Group |
|---|---|
| Process is `openclaw-gateway` | `openclaw-core` |
| Child of gateway with `chrome` or `chromium` in cmdline | `openclaw-browser` |
| Child of gateway, other | `openclaw-core` |
| Grandchild+ of gateway | `openclaw-agent` |
| Manually registered via API with explicit group | (as specified) |
| Everything else on the machine | not tracked (filtered out) |

#### GPU Metrics (pynvml, RTX 3090)

```python
import pynvml
pynvml.nvmlInit()
handle = pynvml.nvmlDeviceGetHandleByIndex(0)

util    = pynvml.nvmlDeviceGetUtilizationRates(handle)  # .gpu (%), .memory (%)
mem     = pynvml.nvmlDeviceGetMemoryInfo(handle)         # .used, .total (bytes)
power   = pynvml.nvmlDeviceGetPowerUsage(handle)         # milliwatts → divide by 1000
```

Stored as `grp='gpu'` rows in `metrics`. GPU is machine-level — cannot be attributed per-process without NVIDIA MIG or cgroups, which are out of scope for v1. GPU use by Qwen will appear in the GPU timeline and is clearly visible without per-process attribution.

#### Disk Monitoring

Configured directories to track (defined in `collector/config.py`, editable):

```python
DISK_DIRS = {
    "openclaw-workspace": "~/.openclaw/workspace",
    "openclaw-sessions":  "~/.openclaw/sessions",
    "openclaw-media":     "~/.openclaw/media",
    "openclaw-logs":      "~/.openclaw/logs",     # if it exists
    "monitor-db":         "~/.openclaw/claw-monitor",
    "openclaw-total":     "~/.openclaw",           # entire openclaw dir
}
# Excluded: ~/work/claw-monitor (the tool itself)
# Qwen models (~19GB static) tracked separately as a one-time size fact
```

Each 60s, writes total bytes and file count per key. Sessions dir in particular is expected to grow over time and is the primary disk sizing signal.

journald logs for OpenClaw services tracked via `journalctl --disk-usage` (one subprocess call per 60s, low cost).

#### Known Limitations

- **PID churn at 1s**: Processes that spawn and die within 1 second are missed. Acceptable — such processes contribute negligible cumulative resources. Token tracking via API is unaffected.
- **No per-PID network I/O**: Machine-level only. Per-PID network requires libpcap or cgroups — v2 candidate.
- **No per-process GPU**: Machine-level only. GPU use is dominated by Qwen when running; absence/presence is clearly visible.
- **First CPU sample after PID registration**: NULL (delta requires two readings).
- **Disk scan cost**: `os.walk()` on large directories can take 1–2s. Runs in slow loop (60s cycle), so does not block fast loop.

---

### 2. `web/` — Next.js app (TypeScript)

- **Framework:** Next.js 14 (App Router), React, Radix UI Themes, Recharts
- **Port:** **7432** (permanent, bound to 0.0.0.0)
- **Process manager:** `claw-web.service` (systemd user scope)
- **DB access:** `better-sqlite3` (synchronous, WAL mode)

#### Middleware: Tailscale IP Guard

All routes reject requests not from:
- `127.0.0.1` / `::1` (localhost)
- `100.64.0.0/10` (Tailscale CGNAT range)

Returns `403 Forbidden` otherwise.

#### Pricing Config

`web/src/lib/pricing.json` — maps model IDs to per-token costs (USD). Updated manually.

```json
{
  "claude-sonnet-4-6": { "input_per_mtok": 3.00, "output_per_mtok": 15.00 },
  "claude-haiku-4-5":  { "input_per_mtok": 0.25, "output_per_mtok": 1.25 },
  "gpt-5.2":           { "input_per_mtok": 5.00, "output_per_mtok": 15.00 },
  "gpt-4o-mini":       { "input_per_mtok": 0.15, "output_per_mtok": 0.60 }
}
```

---

## OpenClaw → Monitor Integration

### Design Principle: Minimal Coupling

**The collector does the heavy lifting.** It autodiscovers all OpenClaw PIDs by scanning `/proc/*/cmdline` for `openclaw-gateway` on startup and walking the child process tree. Resource attribution (CPU%, RAM, net) happens entirely in the collector — OpenClaw does not need to report this.

**OpenClaw provides two things the collector cannot infer:**
1. **Tags** — what kind of work is happening (the collector can see CPU spikes but not *why*)
2. **Token counts** — LLM token usage is invisible to the OS; OpenClaw is the only source of truth

Everything else (PID registration, process groups) is handled automatically. The optional `POST /api/registry/process` endpoint exists for edge cases where OpenClaw spawns a tool that is not a child process of the gateway, but this is rarely needed.

### Tagging: The Work-Type Context System

Tags annotate the timeline with human-readable context. They appear as colored overlays on all time-series charts. A tag is in effect from its timestamp until the next tag (or session end).

**Tag categories:**

| Category | Meaning |
|---|---|
| `conversation` | Active user conversation (reading, thinking, replying) |
| `coding` | Running a coding agent (Claude Code, Codex, OpenCode) |
| `research` | Web searches, reading pages, document analysis |
| `agent` | Spawned a subagent doing autonomous work |
| `heartbeat` | Heartbeat / background check cycle |
| `qwen` | Qwen local LLM is being used |
| `idle` | No meaningful OpenClaw activity |
| `other` | Anything that doesn't fit the above |

**Tag call format:**

```bash
# Fire-and-forget (background, silent failure)
curl -sf -X POST http://localhost:7432/api/tags \
  -H 'Content-Type: application/json' \
  -d '{"category":"conversation","text":"Signal message from David about claw-monitor design","source":"openclaw"}' &
```

**Helper script:** `scripts/tag.sh <category> <text>` — validates category, constructs JSON, fires curl in background, exits 0 always.

### The Remembering Problem — Honest Assessment

Tagging requires OpenClaw to remember to call the API at the right moments. Here is an honest assessment of reliability:

| Trigger | Reliability | Method |
|---|---|---|
| Session start — set initial tag | **High** | Added to AGENTS.md startup routine; happens before any work |
| Spawning a subagent | **High** | Already explicit in my workflow; tag before/after spawn |
| Starting a Qwen session | **High** | Explicit script invocation; easy to add tag call |
| Work type changes mid-conversation | **Medium** | May forget; tag extends until next tag so data is imprecise but not missing |
| Session end / going idle | **Low** | No reliable signal; idle heartbeat from collector is a proxy |

**Mitigation:** Tags are best-effort. The collector always writes idle heartbeats at 60s when no activity is detected, so the timeline never has unexplained gaps. A missed mid-session tag just means the previous tag extends a bit longer than it should — minor accuracy issue, not a data integrity problem.

**What gets added to AGENTS.md:**
A two-line reminder at the top of the "Every Session" section:
```
- Tag your session type at the start: scripts/tag.sh conversation "brief description"
- Tag before spawning agents: scripts/tag.sh agent "agent name and task"
```

### Token Reporting

After each LLM API call that returns token usage metadata, OpenClaw fires:

```bash
curl -sf -X POST http://localhost:7432/api/tokens \
  -H 'Content-Type: application/json' \
  -d "{\"tool\":\"web-search\",\"model\":\"claude-sonnet-4-6\",\"tokens_in\":1500,\"tokens_out\":3200,\"session_id\":\"${SESSION_ID}\"}" &
```

Token reporting is currently manual (OpenClaw calls it explicitly when a tool response includes usage). A future OpenClaw plugin hook could automate this.

### Failure Modes

| Scenario | Impact |
|---|---|
| Monitor not running | All curl calls fail silently. Collector restarts and autodiscovers PIDs. No OpenClaw disruption. |
| Tag missed mid-session | Previous tag extends; timing of work-type boundary is imprecise. Not a data loss. |
| Token call missed | That LLM call's token count is missing from totals. Acceptable. |
| PID reuse | Collector detects via /proc comm mismatch, marks old row unregistered, ignores new process. |
| SQLite contention | WAL mode serializes writes with millisecond waits. No data loss. |

---

## Tagging System

### API

```
POST /api/tags
{
  "category":   "conversation",          // required; must be in allowed set
  "text":       "Signal message: ...",   // required; human-readable description
  "source":     "openclaw",              // required: "openclaw" | "david" | "system" | "auto"
  "session_id": "agent:main:signal:..."  // optional; correlates to an OpenClaw session
  "ts":         <see below>              // optional; defaults to now
}
```

**`ts` field — backdating support:**

| Value | Interpretation |
|---|---|
| Omitted / null | Now (server time at receipt) |
| Number | Unix timestamp (seconds) |
| `"-10m"` / `"-30s"` / `"-2h"` | Relative delta: N minutes/seconds/hours ago |
| `"10 minutes ago"` | Natural language relative (minutes, seconds, hours) |
| `"2026-03-06T08:03:00"` | ISO-8601 absolute |
| Any `Date.parse()`-able string | Parsed as absolute time |

Backdating is useful when you remember what you were doing a few minutes ago but didn't tag it at the time. The tag appears at the correct point on the timeline chart.

**`tag.sh` backdating:**
```bash
tag.sh conversation "was reading the README" david "" -10m
tag.sh coding "debugging the collector" david "" "30 minutes ago"
tag.sh research "reading arxiv paper" david "" "2026-03-06T08:03:00"
```

Tags can also be created manually from the dashboard UI (David can annotate the timeline directly).

### Database

```sql
CREATE TABLE tags (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         INTEGER NOT NULL,
  category   TEXT NOT NULL,   -- 'conversation'|'coding'|'research'|'agent'|'heartbeat'|'qwen'|'idle'|'other'
  text       TEXT NOT NULL,
  source     TEXT NOT NULL,   -- 'openclaw'|'david'|'system'|'auto'
  session_id TEXT
);
CREATE INDEX idx_tags_ts ON tags(ts);
```

### Dashboard Integration

Tags appear as:
- **Vertical lines** on time-series charts at the tag timestamp
- **Colored bands** between consecutive tags (each category has a distinct color)
- **Tag log** panel on the overview page showing recent annotations
- **Tooltip** on hover showing category, text, source, and duration (time until next tag)

---

## Database Schema (SQLite)

```sql
PRAGMA journal_mode=WAL;

-- Fast-loop time-series (written ONLY when OpenClaw activity detected — never during idle)
CREATE TABLE metrics (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ts                INTEGER NOT NULL,
  grp               TEXT NOT NULL,       -- 'openclaw-core'|'openclaw-browser'|'openclaw-agent'|'net'|'gpu'
  cpu_pct           REAL,                -- NULL on first sample; not set for net/gpu rows
  mem_rss_mb        REAL,                -- not set for net/gpu rows
  net_in_kb         REAL,                -- only set when grp='net'
  net_out_kb        REAL,                -- only set when grp='net'
  gpu_util_pct      REAL,                -- only set when grp='gpu'
  gpu_vram_used_mb  REAL,                -- only set when grp='gpu'
  gpu_power_w       REAL,                -- only set when grp='gpu'
  sample_interval_s INTEGER NOT NULL     -- actual elapsed seconds since last write (shows burst vs sustained)
);

-- Single-row collector liveness table (always UPDATE, never INSERT after init)
-- Used by the dashboard to distinguish idle gaps from collector-down gaps
CREATE TABLE collector_status (
  id         INTEGER PRIMARY KEY CHECK (id = 1),  -- enforces single row
  last_seen  INTEGER NOT NULL,                     -- updated every 60s by slow loop
  started_at INTEGER NOT NULL                      -- set on collector startup
);
CREATE INDEX idx_metrics_ts ON metrics(ts);
CREATE INDEX idx_metrics_grp_ts ON metrics(grp, ts);

-- Daily aggregates (retained forever for sizing analysis)
CREATE TABLE metrics_daily (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  date           TEXT NOT NULL,
  grp            TEXT NOT NULL,
  avg_cpu_pct    REAL,
  max_cpu_pct    REAL,
  avg_mem_rss_mb REAL,
  max_mem_rss_mb REAL,
  sum_net_in_kb  REAL,
  sum_net_out_kb REAL,
  avg_gpu_pct    REAL,
  max_gpu_pct    REAL,
  max_vram_mb    REAL,
  UNIQUE(date, grp)
);

-- Disk space snapshots (every 60s regardless of activity)
CREATE TABLE disk_snapshots (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER NOT NULL,
  dir_key     TEXT NOT NULL,      -- e.g. 'openclaw-sessions', 'openclaw-total'
  size_bytes  INTEGER NOT NULL,
  file_count  INTEGER,
  journald_mb REAL                -- only set when dir_key='openclaw-logs'
);
CREATE INDEX idx_disk_ts ON disk_snapshots(ts);

-- Registered processes (optional hints from OpenClaw; mostly auto-discovered)
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
  model      TEXT NOT NULL,
  tokens_in  INTEGER,
  tokens_out INTEGER,
  session_id TEXT
);
CREATE INDEX idx_token_events_ts ON token_events(ts);
CREATE INDEX idx_token_events_tool ON token_events(tool);

-- Work-type annotations
CREATE TABLE tags (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         INTEGER NOT NULL,
  category   TEXT NOT NULL,
  text       TEXT NOT NULL,
  source     TEXT NOT NULL,
  session_id TEXT
);
CREATE INDEX idx_tags_ts ON tags(ts);
```

### Schema Design Notes

- **`process_registry.id` is autoincrement PK** (not `pid`) — handles Linux PID reuse correctly
- **`metrics` contains only active rows** — no idle heartbeat rows; gaps are truly empty
- **`collector_status`** (single row, updated every 60s) lets dashboard distinguish idle gaps from collector-down gaps
- **`sample_interval_s`** records actual elapsed time since last write — shows whether activity was a brief spike or sustained
- **`cost_usd` not stored** — computed at query time from raw token counts + pricing.json
- **`disk_snapshots`** is always written at 60s regardless of activity (disk growth needs continuous tracking)
- **`metrics` grp='gpu'** is machine-level (not per-process); GPU use by Qwen is visible without attribution

---

## API Specification

### `POST /api/tags`
Submit a work-type tag.

**Request:**
```json
{
  "category": "conversation",
  "text": "Signal: David asking about claw-monitor design",
  "source": "openclaw",
  "session_id": "agent:main:signal:direct:+15303386428"
}
```

**Response 201:** `{ "ok": true, "id": 7 }`
**Response 400:** category not in allowed set, or missing required fields.

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
  "session_id": "agent:main:signal:direct:+15303386428"
}
```

**Response 201:** `{ "ok": true, "id": 42 }`

---

### `POST /api/registry/process`
Optional: register a PID explicitly (only needed for processes not autodiscovered).

**Request:**
```json
{
  "pid": 12345,
  "name": "chrome",
  "group": "openclaw-browser",
  "description": "Headless Chrome for web scraping"
}
```

**Response 201:** `{ "ok": true, "registered": 1709712000 }`

---

### `GET /api/metrics`
Query time-series resource data.

**Query params:**

| Param | Type | Default | Notes |
|---|---|---|---|
| `from` | unix ts | required | Start of range |
| `to` | unix ts | now | End of range |
| `group` | string | all | Filter by group |
| `resolution` | string | `auto` | `raw`, `hourly`, `daily` |
| `include_idle` | bool | true | Include idle heartbeat rows |

Auto resolution: `< 6h` → raw, `6h–3d` → hourly, `> 3d` → daily.

**Response 200:**
```json
{
  "data": [
    { "ts": 1709712000, "grp": "openclaw-core", "cpu_pct": 34.2, "mem_rss_mb": 512.3, "sample_interval_s": 1, "is_idle_heartbeat": 0 },
    { "ts": 1709712000, "grp": "net", "net_in_kb": 120.5, "net_out_kb": 45.2, "sample_interval_s": 1, "is_idle_heartbeat": 0 },
    { "ts": 1709712000, "grp": "gpu", "gpu_util_pct": 82.0, "gpu_vram_used_mb": 18432.0, "gpu_power_w": 220.5, "sample_interval_s": 1, "is_idle_heartbeat": 0 }
  ],
  "count": 3,
  "resolution": "raw"
}
```

---

### `GET /api/metrics/stream`
SSE live feed. Emits one event per fast-loop write (activity-gated or 60s idle heartbeat).

**Event format (only emitted when activity detected):**
```
data: {"ts":1709712000,"groups":{"openclaw-core":{"cpu_pct":34.2,"mem_rss_mb":512.3},"openclaw-browser":{"cpu_pct":12.1,"mem_rss_mb":1024.0}},"net":{"in_kb":120.5,"out_kb":45.2},"gpu":{"util_pct":82.0,"vram_used_mb":18432.0,"power_w":220.5},"sample_interval_s":1}
```

During idle periods the SSE connection stays open but no `data:` events are emitted. The `[Live ●]` indicator stays green (connection is alive); charts simply show no new data points. A separate `ping:` keep-alive frame is sent every 30s to prevent proxy timeouts.

---

### `GET /api/disk`
Query disk usage history.

**Query params:** `from`, `to`, `dir_key` (optional filter).

**Response 200:**
```json
{
  "data": [
    { "ts": 1709712000, "dir_key": "openclaw-sessions", "size_bytes": 524288000, "file_count": 1423 },
    { "ts": 1709712000, "dir_key": "openclaw-total", "size_bytes": 612000000, "file_count": 1680 }
  ]
}
```

---

### `GET /api/tags`
Query tag history.

**Query params:** `from`, `to`, `category` (optional filter), `source` (optional filter).

**Response 200:**
```json
{
  "tags": [
    { "id": 7, "ts": 1709712000, "category": "conversation", "text": "Signal: David about claw-monitor", "source": "openclaw", "session_id": "agent:main:..." }
  ]
}
```

---

### `GET /api/tokens/summary`
Aggregate token usage.

**Query params:** `from` (default 24h ago), `to`, `group_by` (`tool`|`model`|`session_id`).

**Response 200:**
```json
{
  "summary": [
    { "tool": "web-search", "total_in": 45000, "total_out": 120000, "call_count": 23, "est_cost_usd": 6.20 }
  ],
  "totals": { "tokens_in": 45000, "tokens_out": 120000, "calls": 23, "est_cost_usd": 6.20 }
}
```

---

## Dashboard Pages

### `/` — Live Overview

```
┌──────────────────────────────────────────────────────────────┐
│  🔭 CLAW MONITOR              [Live ●]  [Last: 2s ago]      │
│  "to help right-size the machine"                            │
├────────────┬────────────┬──────────┬──────────┬─────────────┤
│  CPU        │  Memory    │  GPU      │  Network  │  Disk      │
│  ████░ 62%  │  5.2/64GB  │  82% GPU │ ↓1.2MB/s  │ 612MB used │
│  [spark]    │  [spark]   │  18.4GB  │ ↑340KB/s  │ +2MB today │
│             │            │  VRAM    │  [spark]  │            │
├────────────┴────────────┴──────────┴──────────┴─────────────┤
│  CPU by Group — Last 30 min (stacked area + tag overlays)   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  [■ conversation]  [■ agent]  [■ idle]                │  │
│  │  ████▒▒░░░░░░░░░████████████░░░░░░░░░░░░░░░░░░░░░░░  │  │
│  └────────────────────────────────────────────────────────┘  │
│  Memory — Last 30 min                                        │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  ████████████████████████████████████████████████████  │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  GPU — Last 30 min                                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  GPU util:  ░░░░░░░░░░░░░░░░░████████████░░░░░░░░░░░  │  │
│  │  VRAM:      ░░░░░░░░░░░░░░░░░█████████████████████░░  │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  Recent Tags                                                  │
│  06:33 [conversation] Signal: David claw-monitor design      │
│  07:14 [conversation] Signal: David design review round 2    │
│                                             [→ Full timeline]│
├──────────────────────────────────────────────────────────────┤
│  Today's Token Usage   1.2M in / 3.4M out  Est. $4.20       │
│  Top tool: web-search (42 calls, $2.10)    [→ Full breakdown]│
├──────────────────────────────────────────────────────────────┤
│  Disk (openclaw-total): 612 MB  Sessions: 524 MB  (+2MB/day)│
│                                             [→ Disk detail]  │
└──────────────────────────────────────────────────────────────┘
```

- All time-series charts use time-scale x-axis (handles sparse active data correctly)
- Gaps in charts: cross-referenced against `collector_status.last_seen` — grey = intentional idle, amber warning = collector was down
- Tag overlays: colored bands between consecutive tags; vertical lines at tag boundaries
- `[Live ●]` stays green during idle (SSE connection open, just no data events); turns red only if connection drops; reconnects automatically

---

### `/metrics` — Time-Series Explorer

Full date-range explorer with CPU, memory, GPU, and network charts. Recharts brush selection for zoom. Group filter. Resolution auto or manual. Tag overlays on all charts. Tooltip shows sample_interval_s to indicate data density at any point.

---

### `/disk` — Storage Detail

Timeline chart of `openclaw-total` growth. Stacked bar showing breakdown by subdirectory (sessions, workspace, media, logs, monitor-db). Sessions directory growth rate highlighted as key metric for disk sizing. Table of latest snapshot values per directory.

---

### `/tokens` — Token Usage

Date range selector. Summary stats. By-tool table (sortable). By-model donut chart. Daily bar chart. Session dropdown (filter by session_id). All costs computed client-side from raw counts + pricing.json.

---

### `/processes` — Process Registry

Live process table with alive/dead status. Group breakdown donut. Description tooltips. Active/all filter.

---

### `/tags` — Tag Log

Full tag history with filter by category and source. Timeline view showing tag periods as colored spans. David can add manual tags from this page.

---

## File Layout

```
~/work/claw-monitor/
├── README.md                       ← design document (this file)
├── HISTORY.md                      ← decision log / attribution log
├── schema.sql                      ← run once to initialize SQLite DB
│
├── claw-collector/
│   ├── collector.py                ← main daemon: fast loop + slow loop
│   ├── db.py                       ← SQLite helpers (WAL open, insert, retention)
│   ├── pid_tracker.py              ← /proc PID walker, comm verification, auto-grouping
│   ├── net_tracker.py              ← /proc/net/dev delta computation
│   ├── gpu_tracker.py              ← pynvml wrapper (init, read, close)
│   ├── disk_tracker.py             ← os.walk() directory size scanner
│   ├── config.py                   ← DISK_DIRS config, thresholds (CPU% activity threshold), DB path
│   └── claw-collector.service      ← systemd user unit
│
├── web/
│   ├── package.json
│   ├── next.config.ts              ← port 7432, standalone output
│   ├── tsconfig.json
│   ├── claw-web.service            ← systemd user unit
│   └── src/
│       ├── middleware.ts           ← Tailscale IP guard
│       ├── lib/
│       │   ├── db.ts               ← better-sqlite3 singleton (WAL)
│       │   ├── pricing.json        ← model → cost per mtok
│       │   └── cost.ts             ← cost computation helper
│       ├── app/
│       │   ├── layout.tsx          ← Radix Theme wrapper + nav
│       │   ├── page.tsx            ← / Live Overview
│       │   ├── metrics/page.tsx    ← /metrics Time-Series Explorer
│       │   ├── disk/page.tsx       ← /disk Storage Detail
│       │   ├── tokens/page.tsx     ← /tokens Token Usage
│       │   ├── processes/page.tsx  ← /processes Registry
│       │   ├── tags/page.tsx       ← /tags Tag Log
│       │   └── api/
│       │       ├── tags/route.ts                  ← POST + GET /api/tags
│       │       ├── tokens/route.ts                ← POST /api/tokens
│       │       ├── tokens/summary/route.ts        ← GET /api/tokens/summary
│       │       ├── registry/process/route.ts      ← POST /api/registry/process
│       │       ├── registry/route.ts              ← GET /api/registry
│       │       ├── metrics/route.ts               ← GET /api/metrics
│       │       ├── metrics/stream/route.ts        ← GET /api/metrics/stream (SSE)
│       │       └── disk/route.ts                  ← GET /api/disk
│       └── components/
│           ├── MetricSparkline.tsx
│           ├── CpuAreaChart.tsx          ← stacked area, tag overlays
│           ├── GpuChart.tsx              ← util + VRAM dual-axis line chart
│           ├── DiskChart.tsx             ← stacked bar by directory
│           ├── NetworkChart.tsx          ← in/out line chart
│           ├── TokenTable.tsx
│           ├── TagOverlay.tsx            ← renders colored bands on charts
│           ├── TagLog.tsx                ← recent tags list
│           ├── ProcessTable.tsx
│           ├── LiveIndicator.tsx
│           └── CostBadge.tsx
│
└── scripts/
    ├── tag.sh                      ← OpenClaw integration: post a tag
    └── register-tool.sh            ← OpenClaw integration: register a PID (optional)
```

---

## Deployment

### Prerequisites

- Python 3.10+, pip
- Node.js 20+, npm
- SQLite 3.35+
- NVIDIA drivers + NVML library (`nvidia-smi` available)
- systemd (user scope)
- Tailscale active

### Steps

```bash
# 1. Create DB directory
mkdir -p ~/.openclaw/claw-monitor/

# 2. Initialize DB
sqlite3 ~/.openclaw/claw-monitor/metrics.db < schema.sql

# 3. Install Python deps
cd ~/work/claw-monitor/claw-collector
pip install --user psutil nvidia-ml-py3

# 4. Build Next.js
cd ~/work/claw-monitor/web
npm install && npm run build

# 5. Install systemd units
cp claw-collector/claw-collector.service ~/.config/systemd/user/
cp web/claw-web.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now claw-collector claw-web

# 6. Enable user lingering (services persist without active login)
loginctl enable-linger $USER

# 7. Verify
systemctl --user status claw-collector claw-web
curl -s http://localhost:7432/api/registry | jq .

# 8. Dashboard (from any Tailscale device)
open http://dw-asus-linux.tail3eef35.ts.net:7432
```

### Day-to-Day Ops

```bash
journalctl --user -u claw-collector -f   # collector logs
journalctl --user -u claw-web -f          # web logs
systemctl --user restart claw-collector   # after collector changes
systemctl --user restart claw-web         # after web changes
systemctl --user status claw-*            # both at once
```

---

## Port & Networking

| Service | Port | Bind | Access |
|---|---|---|---|
| Next.js web + API | 7432 | 0.0.0.0 | `http://dw-asus-linux.tail3eef35.ts.net:7432` |

---

## Open Questions (All Resolved)

| # | Question | Decision |
|---|---|---|
| 1 | Python vs Rust for collector? | Python — I/O-bound, psutil robust, <300 lines |
| 2 | Token cost storage? | Raw counts only; compute USD via pricing.json at query time |
| 3 | Data retention? | 14 days full-res, daily aggregates forever |
| 4 | Auth? | Tailscale + IP range middleware |
| 5 | PM2 vs systemd? | systemd user scope |
| 6 | WebSocket vs SSE? | SSE |
| 7 | Fixed vs adaptive interval? | 1s sweep always; write to `metrics` ONLY on activity (CPU > 1%); zero rows during idle; `collector_status` pings every 60s to indicate liveness |
| 8 | GPU included? | Yes — pynvml, machine-level, grp='gpu' |
| 9 | Disk monitoring? | Yes — 60s slow loop, per-directory, exclude ~/work/claw-monitor |
| 10 | Tagging system? | Yes — POST /api/tags, overlays on all charts, manual + automatic |

---

## Known Issues / Bug Fixes

### Fixed 2026-03-06: CPU% and Memory summary stat display bugs

**Root cause:** `page.tsx` was accumulating `latestCpu` and `latestMem` across every row returned for the last 30 minutes (up to ~1800 rows × N groups), instead of using only the most recent timestamp's rows for the point-in-time summary cards.

- **CPU symptom:** Stat card showed ~27,892% — 30 min of rows × all groups summed together
- **Memory symptom:** Stat card showed ~1,130 GB — same accumulation bug, then divided by 1024 to "convert to GB"

**Fix (frontend only — collector data was correct):**
- Find `latestTs = max(row.ts)` across all returned rows
- Filter to only `rows where ts === latestTs` for stat card values
- CPU display changed to **"X.XX cores"** (sum of cpu_pct / 100), which is more intuitive for sizing questions than a % that can exceed 100% on multi-threaded workloads
- Memory display correctly reads RSS (VmRSS) in MB, divided by 1024 for GB, labeled "RSS (now)"

---

## Not In Scope (v1)

- Per-PID network I/O (requires libpcap or eBPF — v2 candidate)
- Per-process GPU attribution (requires NVIDIA MIG or cgroups — v2)
- Alert / notification system
- Multi-machine monitoring
- Per-request latency tracking
- Authentication beyond Tailscale + IP middleware
