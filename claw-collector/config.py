"""Configuration for claw-collector."""

import os

DB_PATH = os.path.expanduser("~/.openclaw/claw-monitor/metrics.db")

# Activity threshold: write to metrics only when any OpenClaw PID CPU% exceeds this
ACTIVITY_THRESHOLD_PCT = 1.0

# Fast loop interval (seconds)
FAST_LOOP_INTERVAL = 1

# Slow loop interval (seconds)
SLOW_LOOP_INTERVAL = 60

# Retention: delete metrics older than this many days
RETENTION_DAYS = 14

# Directories to track for disk usage
DISK_DIRS = {
    "openclaw-workspace": os.path.expanduser("~/.openclaw/workspace"),
    "openclaw-sessions":  os.path.expanduser("~/.openclaw/sessions"),
    "openclaw-media":     os.path.expanduser("~/.openclaw/media"),
    "openclaw-logs":      os.path.expanduser("~/.openclaw/logs"),
    "monitor-db":         os.path.expanduser("~/.openclaw/claw-monitor"),
    "openclaw-total":     os.path.expanduser("~/.openclaw"),
}

# Gateway process name to search for in /proc
GATEWAY_CMDLINE_MATCH = "openclaw-gateway"
