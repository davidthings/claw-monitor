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
  CM_DB_PATH="/tmp/claw-test-$$.db" python3 -m pytest tests/ -v --tb=short "$@"
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
  cd "$ROOT"
  python3 -m pytest tests/integration/ -v --timeout=60
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
