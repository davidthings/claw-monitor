#!/usr/bin/env bash
# register-tool.sh — Register a PID with claw-monitor
# Usage: register-tool.sh <pid> <name> <group> [description]
# Always exits 0 (fire-and-forget)

set -e

MONITOR_URL="${CLAW_MONITOR_URL:-http://localhost:7432}"

pid="${1:-}"
name="${2:-}"
group="${3:-}"
description="${4:-}"

if [ -z "$pid" ] || [ -z "$name" ] || [ -z "$group" ]; then
  echo "Usage: register-tool.sh <pid> <name> <group> [description]" >&2
  exit 0
fi

# Build JSON
json="{\"pid\":$pid,\"name\":\"$name\",\"group\":\"$group\""
if [ -n "$description" ]; then
  json="$json,\"description\":\"$description\""
fi
json="$json}"

# Fire and forget
curl -sf -X POST "$MONITOR_URL/api/registry/process" \
  -H 'Content-Type: application/json' \
  -d "$json" >/dev/null 2>&1 &

exit 0
