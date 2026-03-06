#!/usr/bin/env bash
# run-tests.sh — run the full claw-monitor test suite
# Usage: ./run-tests.sh [--unit] [--integration] [--web]
# Default: unit tests only (Python + Next.js). Pass --integration to include live tests.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
FAILED=0

run_python_unit() {
  echo "=== Python unit tests ==="
  cd "$ROOT/claw-collector"
  CM_DB_PATH="/tmp/claw-test-$$.db" python -m pytest tests/ -v --tb=short "$@"
  cd "$ROOT"
}

run_web_unit() {
  echo "=== Next.js unit tests ==="
  cd "$ROOT/web"
  CM_DB_PATH="/tmp/claw-test-$$.db" npx vitest run "$@"
  cd "$ROOT"
}

run_integration() {
  echo "=== Integration tests ==="
  export CM_DB_PATH="/tmp/claw-test-integ-$$.db"
  export CM_PORT=17432
  export CM_SLOW_LOOP_INTERVAL_S=1
  sqlite3 "$CM_DB_PATH" < "$ROOT/schema.sql"
  python3 "$ROOT/claw-collector/collector.py" &
  CPID=$!
  (cd "$ROOT/web" && CM_PORT=$CM_PORT CM_DB_PATH=$CM_DB_PATH npm run start) &
  WPID=$!
  sleep 3
  python -m pytest "$ROOT/tests/integration/" -v --timeout=60 "$@" || FAILED=1
  kill $CPID $WPID 2>/dev/null || true
  rm -f "$CM_DB_PATH"
  return $FAILED
}

MODE="unit"
for arg in "$@"; do
  case $arg in
    --integration) MODE="integration" ;;
    --web)         MODE="web" ;;
    --unit)        MODE="unit" ;;
  esac
done

case $MODE in
  unit)        run_python_unit; run_web_unit ;;
  web)         run_web_unit ;;
  integration) run_python_unit; run_web_unit; run_integration ;;
esac

echo ""
echo "Done."
