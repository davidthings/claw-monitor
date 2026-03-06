# claw-monitor — UI Specification

---

## Overview Page (`/`)

The Overview page is the primary view. It answers the question: **what is OpenClaw doing right now, and what has it been doing?**

---

### Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  STAT CARDS (top row)                                           │
│  [CPU]  [MEMORY]  [GPU]  [DISK]  [TOKENS]                       │
├─────────────────────────────────────────────────────────────────┤
│  COMBINED RESOURCE CHART (main panel)                           │
│                                                                 │
│  One line per resource, all on a single chart                   │
│  Time axis at bottom                                            │
│  Tag markers along the time axis                                │
└─────────────────────────────────────────────────────────────────┘
```

---

### Stat Cards

Five cards displayed in a row across the top:

| Card | Value | Subtext |
|------|-------|---------|
| CPU | `X.XX cores` | `OpenClaw total (now)` |
| Memory | `X.XXGB` | `of YYGb RSS (now)` |
| GPU | `XX%` | `X.XGB VRAM (now)` |
| Disk | `XXXMB` | `openclaw total` |
| Tokens | `XX tok/min` | `current rate` |

- Values update live via SSE (same mechanism as current)
- Tokens card shows the **current tokens/minute rate** — computed as total tokens (in + out) from `token_events` in the last 60 seconds
- If no token events in the last 60 seconds, shows `0 tok/min`
- If GPU is unavailable, GPU card shows `—` and is visually dimmed (same as current)

---

### Combined Resource Chart

A single time-series chart with one summary line per resource. All resources share the same horizontal time axis. Each line is normalized or expressed in its natural unit — no normalisation to a common scale; instead, use **dual or multi-axis** (right/left) as needed, or accept that lines will be at different scales and labelled clearly.

#### Lines

| Line | Colour | Data source | Unit |
|------|--------|-------------|------|
| CPU | green | `metrics` — sum of `cpu_pct` across all OpenClaw groups | cores (cpu_pct / 100) |
| Memory | blue | `metrics` — max `mem_rss_mb` across groups at each timestamp | GB |
| GPU | magenta | `metrics` — `gpu_util_pct` from `grp="gpu"` row | % |
| Network | orange | `metrics` — `net_in_kb + net_out_kb` from `grp="net"` row | KB/s |
| Tokens | yellow | `token_events` — rolling count per time bucket | tokens/min |

- Lines are drawn only where data exists. Gaps are gaps (not interpolated).
- The time range defaults to the **last 2 hours**, selectable (same range picker as Metrics page).
- Y-axis: each line uses its own scale, labelled on the axis or in the legend. Avoid overloading a single Y-axis with incompatible units.
- Chart library: Recharts (already in use).

#### Hover Tooltip

When the user hovers over any point on the chart:
- A vertical crosshair line appears at the hovered timestamp
- A tooltip displays **all resource values at that timestamp**:
  ```
  10:47:23 AM
  CPU     0.34 cores
  Memory  1.92 GB
  GPU     72%  /  1.2 GB VRAM
  Network 420 KB/s  (380 in / 40 out)
  Tokens  12 / min
  ```
- If a resource has no row at the exact timestamp, show `—`
- Tooltip follows the cursor (or is anchored near the crosshair)

---

### Tag Markers

Tags from the `tags` table are shown as markers along the **horizontal time axis** of the combined chart.

#### Appearance

- Each tag is a small **vertical tick or triangle** on the time axis at its `ts` timestamp
- The marker is **colour-coded by category**:

| Category | Colour |
|----------|--------|
| `conversation` | sky blue |
| `coding` | amber |
| `research` | teal |
| `agent` | purple |
| `heartbeat` | grey |
| `qwen` | lime |
| `idle` | dark grey |
| `other` | white/neutral |

- Marker height: consistent small tick (e.g. 8px), not proportional to anything
- No ↩ indicator on this chart for backdated tags (that detail lives in the Tag Log page)
- If multiple tags fall within a few pixels of each other, cluster them (stack ticks or group with a count badge)

#### Hover / Popup

- Hovering over a tag marker shows a **popup above the axis** with:
  ```
  10:09 AM  [agent]
  "spawning claw-monitor-builder: test plan round 3"
  ```
- Popup includes: timestamp, category badge (with its colour), and the full tag text
- Clicking a tag marker has no special action (optional: could link to Tags page filtered to that time)

---

### What's Removed from Current Overview

The current Overview page has separate GPU and Network mini-charts below the main CPU chart. These are **removed** — all resources move into the single combined chart. The current overview also has no Tokens card or tag markers. Those are **added**.

---

### Data Queries

The Overview page makes the following API calls on load, then subscribes to SSE for live updates:

| Data | Endpoint | Notes |
|------|----------|-------|
| Stat card values | `GET /api/metrics?from=<now-5>&to=<now>&resolution=raw` | Latest row per group |
| Tokens today | `GET /api/tokens/summary?from=<today_midnight>&to=<now>&group_by=tool` | Sum across all tools |
| Chart data | `GET /api/metrics?from=<range_start>&to=<now>&resolution=auto` | All groups |
| Tag markers | `GET /api/tags?from=<range_start>&to=<now>` | All tags in range |
| Live updates | `GET /api/metrics/stream` (SSE) | Appends new rows, updates stat cards |

---

### Design Decisions (resolved)

1. **Y-axis strategy** — CPU + Memory on the left axis; GPU% + Network on the right axis. Tokens on the right axis alongside GPU (both are activity-rate indicators). Recharts dual Y-axis handles this cleanly.

2. **Token line** — Shown as a **smoothed line** (e.g. Recharts `type="monotone"` with a rolling average applied on the client). Bucketed to the chart's time resolution; sparse periods interpolate smoothly rather than dropping to zero.

3. **Tag clustering threshold** — 8px. Tags within 8px of each other on the time axis are grouped into a cluster marker with a count badge. Hovering the cluster shows a stacked list of all tags in the group.

4. **Time range** — Selectable, using the **same range picker as the Metrics page** (e.g. Last 30m / 1h / 2h / 6h / 24h / custom). No hardcoded default — persist the last-used range in `localStorage`.

---

*Spec authored: 2026-03-06. No implementation yet.*
