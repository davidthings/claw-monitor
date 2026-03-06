#!/usr/bin/env bash
# tag.sh — Post a work-type tag to claw-monitor
# Usage: tag.sh <category> <text> [source] [session_id]
# Always exits 0 (fire-and-forget)

set -e

MONITOR_URL="${CLAW_MONITOR_URL:-http://localhost:7432}"
VALID_CATEGORIES="conversation coding research agent heartbeat qwen idle other"

category="${1:-}"
text="${2:-}"
source="${3:-openclaw}"
session_id="${4:-}"

if [ -z "$category" ] || [ -z "$text" ]; then
  echo "Usage: tag.sh <category> <text> [source] [session_id]" >&2
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

# Build JSON
json="{\"category\":\"$category\",\"text\":\"$text\",\"source\":\"$source\""
if [ -n "$session_id" ]; then
  json="$json,\"session_id\":\"$session_id\""
fi
json="$json}"

# Fire and forget
curl -sf -X POST "$MONITOR_URL/api/tags" \
  -H 'Content-Type: application/json' \
  -d "$json" >/dev/null 2>&1 &

exit 0
