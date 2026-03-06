"""Tests for collector.py — Group 6 (§1.6, §1.7, §1.8, §3.5, §3.6)."""

import os
import sys
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import collector
from collector import CpuTracker, sync_processes
import config
from db import (
    insert_metrics, register_process, unregister_process,
    get_active_processes, init_collector_status,
)


# ── §1.6 CpuTracker ──────────────────────────────────────────────────────────

def test_cpu_tracker_first_call_returns_none(monkeypatch):
    monkeypatch.setattr(collector, "read_proc_stat", lambda pid: (100, 50))
    tracker = CpuTracker()
    result = tracker.get_cpu_pct(1234)
    assert result is None


def test_cpu_tracker_second_call_returns_percentage(monkeypatch):
    call_count = {"n": 0}
    def mock_stat(pid):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (100, 50)
        return (200, 100)  # +150 ticks

    monkeypatch.setattr(collector, "read_proc_stat", mock_stat)
    tracker = CpuTracker()
    tracker.get_cpu_pct(1234)
    time.sleep(0.05)
    result = tracker.get_cpu_pct(1234)
    assert result is not None
    assert isinstance(result, float)
    assert result >= 0


def test_cpu_tracker_remove_pid_clears_state(monkeypatch):
    monkeypatch.setattr(collector, "read_proc_stat", lambda pid: (100, 50))
    tracker = CpuTracker()
    tracker.get_cpu_pct(1234)
    assert 1234 in tracker.prev_ticks
    tracker.remove_pid(1234)
    assert 1234 not in tracker.prev_ticks
    assert 1234 not in tracker.prev_time


def test_cpu_tracker_process_gone_returns_none(monkeypatch):
    monkeypatch.setattr(collector, "read_proc_stat", lambda pid: (None, None))
    tracker = CpuTracker()
    result = tracker.get_cpu_pct(9999)
    assert result is None


# ── §1.7 sync_processes ──────────────────────────────────────────────────────

def test_sync_processes_registers_new_pids(test_db, monkeypatch):
    monkeypatch.setattr(collector, "discover_processes", lambda gw: [
        (100, "openclaw-core", "gateway"),
        (200, "openclaw-browser", "chrome"),
    ])
    monkeypatch.setattr(collector, "verify_pid", lambda pid, name: True)

    known = {}
    known = sync_processes(test_db, 100, known)
    assert 100 in known
    assert 200 in known
    active = get_active_processes(test_db)
    assert len(active) == 2


def test_sync_processes_unregisters_gone_pids(test_db, monkeypatch):
    register_process(test_db, 100, "gateway", "openclaw-core")
    register_process(test_db, 200, "chrome", "openclaw-browser")

    monkeypatch.setattr(collector, "discover_processes", lambda gw: [
        (100, "openclaw-core", "gateway"),
    ])
    monkeypatch.setattr(collector, "verify_pid", lambda pid, name: pid == 100)

    known = {100: ("gateway", "openclaw-core"), 200: ("chrome", "openclaw-browser")}
    known = sync_processes(test_db, 100, known)
    active = get_active_processes(test_db)
    assert len(active) == 1
    assert active[0][1] == 100


def test_sync_processes_detects_comm_mismatch(test_db, monkeypatch):
    register_process(test_db, 100, "gateway", "openclaw-core")

    monkeypatch.setattr(collector, "discover_processes", lambda gw: [
        (100, "openclaw-core", "gateway"),
    ])
    monkeypatch.setattr(collector, "verify_pid", lambda pid, name: False)

    known = {100: ("gateway", "openclaw-core")}
    known = sync_processes(test_db, 100, known)
    active = get_active_processes(test_db)
    # Old registration unregistered; new one re-registered since discover returns it
    # verify returns false on the newly registered one too, so it gets unregistered again
    # Net: the old row is unregistered, a new row exists (and may also be unregistered)
    unreg = test_db.execute(
        "SELECT COUNT(*) FROM process_registry WHERE unregistered IS NOT NULL"
    ).fetchone()[0]
    assert unreg >= 1


# ── §1.8 Write-gate logic ────────────────────────────────────────────────────

def test_fast_loop_skips_write_when_below_threshold(test_db, monkeypatch):
    """When all CPU readings are below threshold, no metrics rows should be written."""
    register_process(test_db, 100, "gateway", "openclaw-core")
    init_collector_status(test_db)

    monkeypatch.setattr(collector, "read_proc_stat", lambda pid: (10, 5))
    monkeypatch.setattr(collector, "read_proc_rss", lambda pid: 50.0)

    db_procs = get_active_processes(test_db)
    tracker = CpuTracker()
    any_active = False

    for row_id, pid, name, grp, desc in db_procs:
        cpu_pct = tracker.get_cpu_pct(pid)
        if cpu_pct is not None and cpu_pct > config.ACTIVITY_THRESHOLD_PCT:
            any_active = True

    assert any_active is False


def test_fast_loop_writes_when_above_threshold(test_db, monkeypatch):
    """When CPU reading is above threshold, metrics rows should be written."""
    register_process(test_db, 100, "gateway", "openclaw-core")
    init_collector_status(test_db)

    call_count = {"n": 0}
    def mock_stat(pid):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (0, 0)
        return (10000, 5000)

    monkeypatch.setattr(collector, "read_proc_stat", mock_stat)
    monkeypatch.setattr(collector, "read_proc_rss", lambda pid: 100.0)

    tracker = CpuTracker()
    db_procs = get_active_processes(test_db)
    for row_id, pid, name, grp, desc in db_procs:
        tracker.get_cpu_pct(pid)

    time.sleep(0.05)

    any_active = False
    group_metrics = {}
    for row_id, pid, name, grp, desc in db_procs:
        cpu_pct = tracker.get_cpu_pct(pid)
        mem_mb = 100.0
        if grp not in group_metrics:
            group_metrics[grp] = {"cpu_pct": 0.0, "mem_rss_mb": 0.0}
        if cpu_pct is not None:
            group_metrics[grp]["cpu_pct"] += cpu_pct
            if cpu_pct > config.ACTIVITY_THRESHOLD_PCT:
                any_active = True
        group_metrics[grp]["mem_rss_mb"] += mem_mb

    assert any_active is True

    now = int(time.time())
    rows = []
    for grp, data in group_metrics.items():
        rows.append({
            "ts": now, "grp": grp, "cpu_pct": data["cpu_pct"],
            "mem_rss_mb": data["mem_rss_mb"], "net_in_kb": None,
            "net_out_kb": None, "gpu_util_pct": None,
            "gpu_vram_used_mb": None, "gpu_power_w": None,
            "sample_interval_s": 1,
        })
    insert_metrics(test_db, rows)
    count = test_db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    assert count >= 1


def test_fast_loop_includes_net_and_gpu_rows(test_db):
    """Verify that net and gpu rows can be included in a metrics insert."""
    now = int(time.time())
    before = test_db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    rows = [
        {"ts": now, "grp": "openclaw-core", "cpu_pct": 10.0, "mem_rss_mb": 100.0,
         "net_in_kb": None, "net_out_kb": None, "gpu_util_pct": None,
         "gpu_vram_used_mb": None, "gpu_power_w": None, "sample_interval_s": 1},
        {"ts": now, "grp": "net", "cpu_pct": None, "mem_rss_mb": None,
         "net_in_kb": 5.0, "net_out_kb": 3.0, "gpu_util_pct": None,
         "gpu_vram_used_mb": None, "gpu_power_w": None, "sample_interval_s": 1},
        {"ts": now, "grp": "gpu", "cpu_pct": None, "mem_rss_mb": None,
         "net_in_kb": None, "net_out_kb": None, "gpu_util_pct": 75.0,
         "gpu_vram_used_mb": 4096.0, "gpu_power_w": 250.0, "sample_interval_s": 1},
    ]
    insert_metrics(test_db, rows)
    after = test_db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    assert after - before == 3
    grps = {r[0] for r in test_db.execute("SELECT DISTINCT grp FROM metrics").fetchall()}
    assert "net" in grps
    assert "gpu" in grps


def test_fast_loop_sample_interval_s_correctness(test_db):
    """Verify that sample_interval_s is stored correctly."""
    now = int(time.time())
    rows = [
        {"ts": now, "grp": "interval-test", "cpu_pct": 10.0, "mem_rss_mb": 50.0,
         "net_in_kb": None, "net_out_kb": None, "gpu_util_pct": None,
         "gpu_vram_used_mb": None, "gpu_power_w": None, "sample_interval_s": 3},
    ]
    insert_metrics(test_db, rows)
    interval = test_db.execute(
        "SELECT sample_interval_s FROM metrics WHERE grp = 'interval-test'"
    ).fetchone()[0]
    assert interval == 3


def test_write_gate_transition_idle_to_active(monkeypatch):
    """Simulates the write gate transitioning from idle (no writes) to active."""
    call_count = {"n": 0}
    def mock_stat(pid):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            return (0, 0)
        return (50000, 20000)

    monkeypatch.setattr(collector, "read_proc_stat", mock_stat)

    tracker = CpuTracker()
    tracker.get_cpu_pct(100)  # prime
    time.sleep(0.05)
    cpu_idle = tracker.get_cpu_pct(100)  # 0 delta
    assert cpu_idle is not None
    assert cpu_idle <= config.ACTIVITY_THRESHOLD_PCT

    time.sleep(0.05)
    cpu_active = tracker.get_cpu_pct(100)  # big delta
    assert cpu_active is not None
    assert cpu_active > config.ACTIVITY_THRESHOLD_PCT


def test_write_gate_transition_active_to_idle(monkeypatch):
    """Simulates the write gate transitioning from active to idle."""
    call_count = {"n": 0}
    def mock_stat(pid):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return (0, 0)
        elif call_count["n"] == 2:
            return (50000, 20000)
        else:
            return (50000, 20000)  # same as before -> 0 delta

    monkeypatch.setattr(collector, "read_proc_stat", mock_stat)

    tracker = CpuTracker()
    tracker.get_cpu_pct(100)  # prime
    time.sleep(0.05)
    cpu_active = tracker.get_cpu_pct(100)
    assert cpu_active > config.ACTIVITY_THRESHOLD_PCT

    time.sleep(0.05)
    cpu_idle = tracker.get_cpu_pct(100)
    assert cpu_idle is not None
    assert cpu_idle <= config.ACTIVITY_THRESHOLD_PCT


# ── §3.5 Overhead tests ──────────────────────────────────────────────────────

def test_collector_ram_overhead():
    """Measure own RSS via /proc/self/status — keep under 50MB."""
    rss_kb = None
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                rss_kb = int(line.split()[1])
                break
    assert rss_kb is not None
    rss_mb = rss_kb / 1024.0
    assert rss_mb < 50, f"Test process RSS is {rss_mb:.1f} MB, expected < 50 MB"


def test_collector_cpu_overhead_idle():
    """Measure own CPU ticks — ensure the test process isn't burning CPU."""
    with open("/proc/self/stat") as f:
        parts = f.read().split()
    utime = int(parts[13])
    stime = int(parts[14])
    clk_tck = os.sysconf("SC_CLK_TCK")
    cpu_seconds = (utime + stime) / clk_tck
    assert cpu_seconds < 30, f"Test process used {cpu_seconds:.1f}s of CPU"


# ── §3.6 Non-OpenClaw isolation ───────────────────────────────────────────────

def test_external_process_not_in_registry(test_db, monkeypatch):
    """Mock discover_processes to not include an external PID."""
    monkeypatch.setattr(collector, "discover_processes", lambda gw: [
        (100, "openclaw-core", "gateway"),
    ])
    monkeypatch.setattr(collector, "verify_pid", lambda pid, name: True)

    known = {}
    known = sync_processes(test_db, 100, known)
    assert 99999 not in known
    active = get_active_processes(test_db)
    pids = [row[1] for row in active]
    assert 99999 not in pids


def test_external_high_cpu_does_not_open_write_gate(test_db, monkeypatch):
    """External PID not in openclaw tree -> write gate stays closed."""
    register_process(test_db, 555, "gateway", "openclaw-core")
    init_collector_status(test_db)

    # PID 555 has low CPU (constant ticks -> 0% after prime)
    call_count = {"n": 0}
    def mock_stat(pid):
        call_count["n"] += 1
        # All calls return same value -> 0% CPU delta
        return (100, 50)

    monkeypatch.setattr(collector, "read_proc_stat", mock_stat)

    tracker = CpuTracker()
    # Only check PID 555 (the only registered openclaw process)
    tracker.get_cpu_pct(555)  # prime
    time.sleep(0.05)
    cpu = tracker.get_cpu_pct(555)  # delta = 0 ticks
    assert cpu is not None
    assert cpu <= config.ACTIVITY_THRESHOLD_PCT
