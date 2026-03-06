# claw-monitor — Instructions

> **Port placeholder:** `CM_PORT` is used throughout this document in place of the actual port number.
> The default port is `7432`. Set the `CM_PORT` environment variable to override.
> Configured in: `web/next.config.mjs` (Next.js) and `web/claw-web.service` (systemd).

---

## Quick Overview

claw-monitor is a lightweight resource monitor for OpenClaw deployments. It runs silently in the background and answers the question: **how much of the host machine does OpenClaw actually use?**

It tracks:
- **CPU** — per process group (gateway, browser, agents), expressed as core-equivalents
- **Memory** — RSS (actual RAM in use) per process group
- **Network** — machine-level bytes in/out
- **GPU** — utilisation %, VRAM used, power draw (NVIDIA; skipped gracefully if absent)
- **Disk** — size of OpenClaw directories over time (sessions, workspace, media, logs)
- **Tokens** — LLM token consumption per tool call (reported by clawbot)
- **Tags** — work-type annotations so resource charts can be interpreted in context

Data is stored in SQLite. A Next.js dashboard is served on a permanent port (`CM_PORT`) accessible from any Tailscale-linked device.

The collector is activity-gated: it writes data only when OpenClaw is active, so idle periods (overnight, etc.) produce no rows and no overhead. A single-row liveness table is updated every 60 seconds so the dashboard can distinguish intentional idle gaps from collector downtime.

---

## Installation

### Prerequisites

- Python 3.10+
- Node.js 20+ and npm
- SQLite 3.35+
- systemd (user scope)
- Tailscale (for remote dashboard access)
- NVIDIA drivers + `nvidia-smi` accessible (optional — GPU tracking is skipped if NVML is unavailable)

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/davidthings/claw-monitor.git ~/work/claw-monitor

# 2. Create the database directory
mkdir -p ~/.openclaw/claw-monitor/

# 3. Initialise the database
sqlite3 ~/.openclaw/claw-monitor/metrics.db < ~/work/claw-monitor/schema.sql

# 4. Install Python dependencies
pip install --user psutil nvidia-ml-py3

# 5. Install Node.js dependencies and build the web app
cd ~/work/claw-monitor/web
npm install
npm run build

# 6. Install and enable systemd user units
cp ~/work/claw-monitor/claw-collector/claw-collector.service ~/.config/systemd/user/
cp ~/work/claw-monitor/web/claw-web.service ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now claw-collector claw-web

# 7. Allow services to run without an active login session
loginctl enable-linger $USER

# 8. Verify both services are running
systemctl --user status claw-collector claw-web

# 9. Confirm the API is responding
curl -s http://localhost:CM_PORT/api/registry | head -c 200
```

### Dashboard Access

- **Locally:** `http://localhost:CM_PORT`
- **Over Tailscale:** `http://<hostname>.tail<id>.ts.net:CM_PORT`

The dashboard is protected by IP-range middleware that only allows Tailscale CGNAT addresses (100.64.0.0/10) and localhost. No additional authentication is required.

### Useful Commands

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

## Instructions for Clawbot

This section is for the OpenClaw AI assistant (clawbot) running on the same machine. It describes how to integrate with claw-monitor as part of normal operation.

### Design Principle

**You do not need to report most things.** The collector automatically discovers all OpenClaw processes via `/proc` and attributes CPU, memory, and network without any help from you. Your role is to provide the two things the OS cannot see:

1. **Tags** — what kind of work is happening right now
2. **Token counts** — LLM token usage per tool call

Both are fire-and-forget: always background (`&`), always exit 0, and never block your response.

---

### Tagging

Tags annotate the resource timeline so charts can be interpreted later. A tag is in effect from its timestamp until the next tag.

**Add this to your session startup routine** (before anything else):

```bash
~/work/claw-monitor/scripts/tag.sh conversation "brief description of this session"
```

**Tag when spawning an agent or starting a long task:**

```bash
~/work/claw-monitor/scripts/tag.sh agent "spawning claw-monitor-builder to build X"
# ... do work ...
~/work/claw-monitor/scripts/tag.sh conversation "back from agent — reviewing results"
```

**Tag when starting or stopping a local LLM:**

```bash
~/work/claw-monitor/scripts/tag.sh qwen "starting Qwen 35B for private research task"
```

#### Tag Categories

| Category | When to use |
|---|---|
| `conversation` | Active session — reading messages, thinking, replying |
| `coding` | Running a coding agent (Claude Code, Codex, OpenCode) |
| `research` | Web searches, reading pages, document analysis |
| `agent` | Spawned a subagent doing autonomous work |
| `heartbeat` | Background heartbeat / periodic check cycle |
| `qwen` | Local LLM (Qwen or similar) is active |
| `idle` | No meaningful activity |
| `other` | Anything else |

#### Script Usage

```bash
tag.sh <category> <text> [source] [session_id] [ts]
```

- `source` defaults to `clawbot` — leave it as the default unless the tag comes from the user
- `session_id` is optional; use the OpenClaw session key if you have it
- `ts` is optional; omit to tag now (see backdating below)

#### Backdating

If you forgot to tag something earlier, backdate it:

```bash
tag.sh conversation "was reading the README" clawbot "" -10m
tag.sh coding "debugging the collector" clawbot "" "30 minutes ago"
tag.sh research "reading design doc" clawbot "" "2026-03-06T08:03:00"
```

Backdated tags appear at the specified time on the chart. A small `↩` indicator appears in the tag log — no annotation on the chart itself.

#### Reliability Expectations

| Trigger | Expected reliability |
|---|---|
| Session start tag | High — put it in your startup routine |
| Agent spawn/return tag | High — you know when you're doing it |
| Local LLM start/stop | High — explicit action |
| Mid-session work type change | Medium — you may occasionally forget |
| Session end / idle | Low — no reliable signal; leave it |

Tags are best-effort. A missed mid-session tag just extends the previous one a little longer. It is not a data integrity problem.

---

### Token Reporting

After any LLM tool call that returns token usage metadata, report it:

```bash
~/work/claw-monitor/scripts/register-tool.sh tokens \
  <tool-name> <model-id> <tokens-in> <tokens-out> [session-id]
```

Example:

```bash
~/work/claw-monitor/scripts/register-tool.sh tokens \
  web-search claude-sonnet-4-6 1500 3200 agent:main:signal:direct
```

- Only call this when you have actual token counts from the API response
- Do not call it on failed tool calls (no tokens consumed)
- The call is fire-and-forget — if claw-monitor is down, it fails silently

---

### Optional: Process Registration

You usually do not need this. The collector finds all OpenClaw processes automatically.

Use it only if you spawn a tool that is **not a child process of openclaw-gateway** and you want it attributed to OpenClaw rather than appearing as untracked system activity:

```bash
~/work/claw-monitor/scripts/register-tool.sh process \
  <pid> <process-name> <group> [description]

# Example
~/work/claw-monitor/scripts/register-tool.sh process \
  12345 python3 openclaw-agent "standalone data pipeline"
```

---

### Summary Checklist

Add these two lines to your operating instructions (e.g. AGENTS.md):

```
- At session start: ~/work/claw-monitor/scripts/tag.sh conversation "brief description"
- Before spawning agents: ~/work/claw-monitor/scripts/tag.sh agent "agent name and task"
```

Everything else is automatic.
