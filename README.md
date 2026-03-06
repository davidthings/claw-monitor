# claw-monitor

> **Status: PLANNING PHASE — No code written yet. Awaiting David's review before implementation.**

A lightweight, always-on resource monitor for OpenClaw. Tracks CPU, memory, network I/O, and token consumption attributable to the OpenClaw process tree — second by second — and exposes a real-time dashboard accessible from any Tailscale-linked device.

---

## Goals

1. **Attribution**: Know exactly how much of the machine's CPU, RAM, and network is consumed by OpenClaw (gateway, headless Chrome, agents, OS utilities) vs. everything else.
2. **Token visibility**: Track LLM token usage per external tool call, registered dynamically as tools are used.
3. **Low overhead**: Collector runs at low priority (nice +10 or similar), polls every 10s, fire-and-forget.
4. **Persistent dashboard**: Available 24/7 on a fixed Tailscale-reachable port.
5. **Dynamic registration**: OpenClaw can trivially register new PIDs/tools with a single lightweight API call — no continuous overhead.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  OpenClaw (gateway + Chrome + agents)                   │
│  ↓ fire-and-forget POST (one per new tool/PID)          │
├─────────────────────────────────────────────────────────┤
│  claw-monitor-api  (Next.js API routes, port 7432)      │
│  ├── /api/registry  ← tool/PID registration             │
│  ├── /api/metrics   ← query historical data             │
│  └── /api/tokens    ← token event ingestion             │
├─────────────────────────────────────────────────────────┤
│  claw-collector  (Python daemon, nice +10, every 10s)   │
│  ├── reads /proc (CPU, mem, net per PID)                │
│  ├── resolves PID→group via registry                    │
│  └── writes to SQLite                                   │
├─────────────────────────────────────────────────────────┤
│  SQLite DB  (~/.openclaw/claw-monitor/metrics.db)       │
│  ├── metrics        (time-series: cpu/mem/net by group) │
│  ├── tool_events    (token usage per tool call)         │
│  └── process_registry (known PIDs + tool names)        │
├─────────────────────────────────────────────────────────┤
│  Dashboard  (Next.js + React + Radix UI + Recharts)     │
│  ├── Real-time charts (CPU, mem, network)               │
│  ├── Token usage table per tool                         │
│  ├── Process attribution breakdown                      │
│  └── Live process registry viewer                       │
└─────────────────────────────────────────────────────────┘
```

---

## Components

### 1. `claw-collector/` — Python daemon

- **Language:** Python 3 + psutil + sqlite3 (stdlib)
- **Poll interval:** 10 seconds
- **Priority:** `nice +10` (SCHED_OTHER, low priority)
- **PID tracking:**
  - Bootstrap: discovers openclaw-gateway PID and all children automatically
  - Reads `/proc/<pid>/stat`, `/proc/<pid>/status`, `/proc/<pid>/net/dev` for zero-dependency accuracy
  - Groups: `openclaw-core`, `openclaw-browser`, `openclaw-agent`, `system`, `unknown`
- **Storage:** Writes a compact row to SQLite every 10s per group
- **Startup:** Systemd unit `claw-collector.service` (user scope)

### 2. `web/` — Next.js app (TypeScript)

- **Framework:** Next.js 14 (App Router), React, Radix UI Themes, Recharts
- **Port:** **7432** (permanent, configured in `ecosystem.config.js` for PM2)
- **Process manager:** PM2 (already used for openclaw-gateway? or standalone)
- **API routes (REST):**
  - `POST /api/registry/process` — register a PID with metadata `{pid, name, group, description}`
  - `POST /api/registry/tokens` — log token event `{tool, model, tokens_in, tokens_out, cost_usd?}`
  - `GET  /api/metrics?from=&to=&group=` — query time-series data
  - `GET  /api/registry` — list known processes
  - `GET  /api/tokens/summary` — aggregate token usage
- **Dashboard pages:**
  - `/` — live overview (sparklines, current load, today's token spend)
  - `/metrics` — full time-series explorer with date range
  - `/tokens` — token usage breakdown by tool/model
  - `/processes` — live process registry with status

### 3. OpenClaw integration (trivial)

OpenClaw (me) will make a single fire-and-forget API call when:
- A new agent/tool PID is spawned: `POST /api/registry/process`
- A tool call returns token usage: `POST /api/registry/tokens`

The call pattern: `curl -sf -X POST http://localhost:7432/api/registry/... -d '...' &`

This is a background shell call — zero blocking, zero overhead.

A small helper script `scripts/register-tool.sh` will wrap this for convenience.

---

## Database Schema (SQLite)

```sql
-- Time-series resource metrics
CREATE TABLE metrics (
  id         INTEGER PRIMARY KEY,
  ts         INTEGER NOT NULL,  -- unix timestamp
  grp        TEXT NOT NULL,     -- 'openclaw-core' | 'openclaw-browser' | 'openclaw-agent' | 'system' | 'unknown'
  cpu_pct    REAL,
  mem_rss_mb REAL,
  net_in_kb  REAL,
  net_out_kb REAL
);
CREATE INDEX idx_metrics_ts ON metrics(ts);

-- Registered processes (dynamic)
CREATE TABLE process_registry (
  pid          INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  grp          TEXT NOT NULL,
  description  TEXT,
  registered   INTEGER NOT NULL,
  unregistered INTEGER
);

-- Token usage events
CREATE TABLE token_events (
  id         INTEGER PRIMARY KEY,
  ts         INTEGER NOT NULL,
  tool       TEXT NOT NULL,
  model      TEXT,
  tokens_in  INTEGER,
  tokens_out INTEGER,
  cost_usd   REAL
);
CREATE INDEX idx_token_events_ts ON token_events(ts);
```

---

## Port & Networking

| Service       | Port  | Notes                              |
|--------------|-------|------------------------------------|
| Next.js web  | 7432  | Permanent, PM2-managed, 0.0.0.0   |
| Tailscale    | —     | Exposes 7432 to all tailnet peers |

Access from any Tailscale device: `http://dw-asus-linux.tail3eef35.ts.net:7432`

---

## File Layout

```
~/work/claw-monitor/
├── README.md              ← this file
├── HISTORY.md             ← change log / decisions
├── claw-collector/
│   ├── collector.py       ← main daemon
│   ├── db.py              ← SQLite helpers
│   ├── pid_tracker.py     ← /proc-based PID walker
│   └── claw-collector.service  ← systemd unit
├── web/
│   ├── package.json
│   ├── next.config.ts
│   ├── src/
│   │   ├── app/           ← Next.js App Router pages
│   │   ├── components/    ← Radix + chart components
│   │   └── api/           ← REST API routes
│   └── db/
│       └── queries.ts     ← SQLite query helpers (better-sqlite3)
├── scripts/
│   └── register-tool.sh   ← helper for OpenClaw → monitor API calls
└── ecosystem.config.js    ← PM2 config
```

---

## Open Questions (for review)

1. **Collector language final choice:** Python (psutil) is simplest; Rust (procfs crate) is zero-overhead. Recommendation: Python for v1, can rewrite hot path later.
2. **Token cost tracking:** Do we want to hard-code Anthropic/OpenAI pricing or just store raw token counts and let the dashboard compute?
3. **Data retention:** How long to keep 10s-resolution data? Suggest: full resolution for 7 days, hourly aggregates forever.
4. **Authentication on port 7432:** Tailscale provides network-level auth, so no app-level auth needed unless you disagree.
5. **PM2 vs systemd for Next.js:** PM2 is simpler; systemd is more robust. Preference?
6. **WebSocket vs polling for live dashboard:** SSE (Server-Sent Events) is simplest for Next.js. Recommend SSE at 10s refresh matching collector interval.

---

## Not In Scope (v1)

- GPU usage (could add later)
- Per-request latency tracking
- Multi-machine monitoring
- Alert/notification system
