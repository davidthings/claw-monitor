#!/usr/bin/env bash
# register-tool.sh — Register resources with claw-monitor
# Usage:
#   register-tool.sh <pid> <name> <group> [description]          — register a process
#   register-tool.sh tokens <tool> <model> <in> <out> [session]  — record token usage
# Always exits 0 (fire-and-forget)

set -e

MONITOR_URL="${CLAW_MONITOR_URL:-http://localhost:${CM_PORT:-7432}}"

subcmd="${1:-}"

# Sub-command: tokens
if [ "$subcmd" = "tokens" ]; then
  tool="${2:-}"
  model="${3:-}"
  tokens_in="${4:-}"
  tokens_out="${5:-}"
  session_id="${6:-}"

  if [ -z "$tool" ] || [ -z "$model" ] || [ -z "$tokens_in" ] || [ -z "$tokens_out" ]; then
    echo "Usage: register-tool.sh tokens <tool> <model> <tokens-in> <tokens-out> [session-id]" >&2
    exit 0
  fi

  json="{\"tool\":\"$tool\",\"model\":\"$model\",\"tokens_in\":$tokens_in,\"tokens_out\":$tokens_out"
  if [ -n "$session_id" ]; then
    json="$json,\"session_id\":\"$session_id\""
  fi
  json="$json}"

  curl -sf -X POST "$MONITOR_URL/api/tokens" \
    -H "Content-Type: application/json" \
    -d "$json" >/dev/null 2>&1 &

  exit 0
fi

# Default: process registration
pid="$subcmd"
name="${2:-}"
group="${3:-}"
description="${4:-}"

if [ -z "$pid" ] || [ -z "$name" ] || [ -z "$group" ]; then
  echo "Usage: register-tool.sh <pid> <name> <group> [description]" >&2
  exit 0
fi

json="{\"pid\":$pid,\"name\":\"$name\",\"group\":\"$group\""
if [ -n "$description" ]; then
  json="$json,\"description\":\"$description\""
fi
json="$json}"

curl -sf -X POST "$MONITOR_URL/api/registry/process" \
  -H "Content-Type: application/json" \
  -d "$json" >/dev/null 2>&1 &

exit 0
