"""Integration tests for claw-collector — real subprocess, real DB writes."""

import os
import sys
import time
import sqlite3
import signal
import subprocess

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COLLECTOR_DIR = os.path.join(PROJECT_ROOT, "claw-collector")


def _openclaw_gateway_running():
    """Return True if openclaw-gateway process is found in /proc."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "openclaw-gateway"],
            capture_output=True, text=True
        )
        return result.returncode == 0
    except Exception:
        return False


requires_openclaw = pytest.mark.skipif(
    not os.path.exists("/proc") or True,  # Skip in CI; requires running OpenClaw gateway
    reason="Requires running OpenClaw gateway",
)

skip_if_openclaw_running = pytest.mark.skipif(
    _openclaw_gateway_running(),
    reason="openclaw-gateway is running; write-gate tests require it to be absent",
)


@requires_openclaw
def test_collector_finds_openclaw_gateway_pid():
    """Verify the collector can find the gateway PID in /proc."""
    pass


@skip_if_openclaw_running
def test_write_gate_idle_no_rows(collector_process, integration_db):
    """When OpenClaw gateway is not running, collector should write no metrics rows."""
    time.sleep(3)  # let it run a few cycles
    conn = sqlite3.connect(integration_db)
    count = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    conn.close()
    # No gateway => no activity detected => no metrics rows
    assert count == 0


def test_collector_status_updated(collector_process, integration_db):
    """With CM_SLOW_LOOP_INTERVAL_S=1, collector_status should be updated within a few seconds."""
    time.sleep(3)
    conn = sqlite3.connect(integration_db)
    row = conn.execute("SELECT last_seen FROM collector_status WHERE id=1").fetchone()
    conn.close()
    assert row is not None
    assert row[0] > 0


def test_disk_snapshots_written(collector_process, integration_db):
    """Collector should write at least one disk snapshot within a few seconds."""
    time.sleep(4)
    conn = sqlite3.connect(integration_db)
    count = conn.execute("SELECT COUNT(*) FROM disk_snapshots").fetchone()[0]
    conn.close()
    # Disk snapshots happen in slow loop (1s interval); should have at least 1
    assert count >= 1


@skip_if_openclaw_running
def test_gpu_rows_only_when_active(collector_process, integration_db):
    """GPU rows should be absent when no GPU activity (and openclaw not driving workloads)."""
    time.sleep(3)
    conn = sqlite3.connect(integration_db)
    count = conn.execute("SELECT COUNT(*) FROM metrics WHERE grp = 'gpu'").fetchone()[0]
    conn.close()
    assert count == 0
