#!/usr/bin/env bash
# tag.sh — Post a work-type tag to claw-monitor
#
# Usage:
#   tag.sh <category> <text> [source] [session_id] [ts]
#
# ts (optional) — when to timestamp the tag. Formats accepted:
#   -10m              10 minutes ago
#   -30s              30 seconds ago
#   -2h               2 hours ago
#   "10 minutes ago"  natural language
#   1741200000        unix timestamp
#   "2026-03-06T08:03:00"  ISO-8601
#   (omit)            now
#
# Always exits 0 (fire-and-forget).

MONITOR_URL="${CLAW_MONITOR_URL:-http://localhost:7432}"
VALID_CATEGORIES="conversation coding research agent heartbeat qwen idle other"

category="${1:-}"
text="${2:-}"
source="${3:-openclaw}"
session_id="${4:-}"
ts="${5:-}"

if [ -z "$category" ] || [ -z "$text" ]; then
  echo "Usage: tag.sh <category> <text> [source] [session_id] [ts]" >&2
  echo "  ts examples: -10m  -30s  -2h  '10 minutes ago'  1741200000  '2026-03-06T08:03:00'" >&2
  exit 0
fi

# Validate category
valid=false
for c in $VALID_CATEGORIES; do
  if [ "$category" = "$c" ]; then
    valid=true
    break
  fi
done

if [ "$valid" = "false" ]; then
  echo "Invalid category: $category (valid: $VALID_CATEGORIES)" >&2
  exit 0
fi

# Build JSON (ts field only included if provided)
json="{\"category\":\"$category\",\"text\":$(printf '%s' "$text" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),\"source\":\"$source\""
if [ -n "$session_id" ]; then
  json="$json,\"session_id\":\"$session_id\""
fi
if [ -n "$ts" ]; then
  json="$json,\"ts\":$(printf '%s' "$ts" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
fi
json="$json}"

# Fire and forget
curl -sf -X POST "$MONITOR_URL/api/tags" \
  -H 'Content-Type: application/json' \
  -d "$json" >/dev/null 2>&1 &

exit 0
