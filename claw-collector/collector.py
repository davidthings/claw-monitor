#!/usr/bin/env python3
"""claw-collector: resource monitoring daemon for OpenClaw."""

import os
import sys
import time
import signal
import logging
import threading

# Add parent dir for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    ACTIVITY_THRESHOLD_PCT,
    FAST_LOOP_INTERVAL,
    SLOW_LOOP_INTERVAL,
    DISK_DIRS,
)
from db import (
    open_db,
    init_schema,
    init_collector_status,
    update_collector_status,
    insert_metrics,
    insert_disk_snapshot,
    register_process,
    unregister_process,
    get_active_processes,
    run_daily_aggregation,
)
from pid_tracker import (
    find_gateway_pid,
    discover_processes,
    verify_pid,
    read_proc_stat,
    read_proc_rss,
)
from net_tracker import NetTracker
from gpu_tracker import init_gpu, read_gpu, close_gpu
from disk_tracker import scan_directory, get_journald_size

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("collector")

# Globals
running = True
CLK_TCK = os.sysconf("SC_CLK_TCK")


def handle_signal(signum, frame):
    global running
    log.info("Received signal %d, shutting down", signum)
    running = False


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


class CpuTracker:
    """Track per-PID CPU usage via /proc/*/stat deltas."""

    def __init__(self):
        self.prev_ticks = {}  # pid -> (utime + stime)
        self.prev_time = {}   # pid -> wall_time

    def get_cpu_pct(self, pid):
        """Get CPU% for a PID. Returns None on first call for that PID."""
        utime, stime = read_proc_stat(pid)
        if utime is None:
            return None

        total_ticks = utime + stime
        now = time.monotonic()

        if pid not in self.prev_ticks:
            self.prev_ticks[pid] = total_ticks
            self.prev_time[pid] = now
            return None

        dt = now - self.prev_time[pid]
        if dt <= 0:
            return 0.0

        dticks = total_ticks - self.prev_ticks[pid]
        cpu_pct = (dticks / CLK_TCK) / dt * 100.0

        self.prev_ticks[pid] = total_ticks
        self.prev_time[pid] = now
        return round(cpu_pct, 2)

    def remove_pid(self, pid):
        self.prev_ticks.pop(pid, None)
        self.prev_time.pop(pid, None)


def sync_processes(conn, gateway_pid, known_pids):
    """Sync process registry with actual /proc state."""
    # Discover current processes
    current = discover_processes(gateway_pid)
    current_pids = {p[0] for p in current}

    # Register new processes
    for pid, grp, comm in current:
        if pid not in known_pids:
            register_process(conn, pid, comm, grp)
            known_pids[pid] = (comm, grp)
            log.info("Registered PID %d (%s) as %s", pid, comm, grp)

    # Verify existing processes
    db_procs = get_active_processes(conn)
    for row_id, pid, name, grp, desc in db_procs:
        if not verify_pid(pid, name):
            unregister_process(conn, row_id)
            known_pids.pop(pid, None)
            log.info("Unregistered PID %d (%s) — gone or comm mismatch", pid, name)

    return known_pids


def slow_loop(conn_factory):
    """Slow loop: disk stats + collector_status update + daily aggregation."""
    last_daily = None

    while running:
        try:
            conn = conn_factory()
            now = int(time.time())

            # Disk snapshots
            for dir_key, path in DISK_DIRS.items():
                size_bytes, file_count = scan_directory(path)
                journald = None
                if dir_key == "openclaw-logs":
                    journald = get_journald_size()
                insert_disk_snapshot(conn, now, dir_key, size_bytes, file_count, journald)

            # Update collector_status
            update_collector_status(conn)

            # Daily aggregation (once per day)
            today = time.strftime("%Y-%m-%d")
            if last_daily != today:
                run_daily_aggregation(conn)
                last_daily = today
                log.info("Daily aggregation complete")

            conn.close()
        except Exception as e:
            log.error("Slow loop error: %s", e)

        # Sleep in small increments to allow clean shutdown
        for _ in range(SLOW_LOOP_INTERVAL):
            if not running:
                break
            time.sleep(1)


def main():
    global running

    log.info("claw-collector starting")

    # Open DB and init
    conn = open_db()
    init_schema(conn)
    init_collector_status(conn)
    log.info("DB initialized")

    # Init GPU
    gpu_available = init_gpu()

    # Find gateway
    gateway_pid = find_gateway_pid()
    if gateway_pid:
        log.info("Gateway PID: %d", gateway_pid)
    else:
        log.warning("Gateway not found — will keep scanning")

    # Init trackers
    cpu_tracker = CpuTracker()
    net_tracker = NetTracker()
    known_pids = {}  # pid -> (comm, grp)
    last_write_ts = 0

    # Start slow loop thread
    def conn_factory():
        return open_db()

    slow_thread = threading.Thread(target=slow_loop, args=(conn_factory,), daemon=True)
    slow_thread.start()

    # Fast loop
    rescan_counter = 0
    while running:
        loop_start = time.monotonic()

        try:
            # Periodically rescan for gateway if not found
            if not gateway_pid or rescan_counter >= 30:
                new_gw = find_gateway_pid()
                if new_gw and new_gw != gateway_pid:
                    gateway_pid = new_gw
                    log.info("Gateway PID updated: %d", gateway_pid)
                elif not new_gw and gateway_pid:
                    # Check if gateway is still alive
                    if not os.path.exists(f"/proc/{gateway_pid}"):
                        log.warning("Gateway PID %d gone", gateway_pid)
                        gateway_pid = None
                rescan_counter = 0
            rescan_counter += 1

            # Sync processes
            known_pids = sync_processes(conn, gateway_pid, known_pids)

            # Reload from DB (catch API registrations)
            db_procs = get_active_processes(conn)

            # Collect per-group metrics
            group_metrics = {}  # grp -> {cpu_pct, mem_rss_mb}
            any_active = False

            for row_id, pid, name, grp, desc in db_procs:
                cpu_pct = cpu_tracker.get_cpu_pct(pid)
                mem_mb = read_proc_rss(pid)

                if grp not in group_metrics:
                    group_metrics[grp] = {"cpu_pct": 0.0, "mem_rss_mb": 0.0}

                if cpu_pct is not None:
                    group_metrics[grp]["cpu_pct"] += cpu_pct
                    if cpu_pct > ACTIVITY_THRESHOLD_PCT:
                        any_active = True
                if mem_mb is not None:
                    group_metrics[grp]["mem_rss_mb"] += mem_mb

            # Net delta
            net_delta = net_tracker.get_delta()

            # GPU
            gpu_data = read_gpu() if gpu_available else None

            # Write if active
            if any_active:
                now = int(time.time())
                interval = max(1, now - last_write_ts) if last_write_ts > 0 else 1

                rows = []
                for grp, data in group_metrics.items():
                    rows.append({
                        "ts": now,
                        "grp": grp,
                        "cpu_pct": round(data["cpu_pct"], 2),
                        "mem_rss_mb": round(data["mem_rss_mb"], 1),
                        "net_in_kb": None,
                        "net_out_kb": None,
                        "gpu_util_pct": None,
                        "gpu_vram_used_mb": None,
                        "gpu_power_w": None,
                        "sample_interval_s": interval,
                    })

                # Net row
                if net_delta:
                    rows.append({
                        "ts": now,
                        "grp": "net",
                        "cpu_pct": None,
                        "mem_rss_mb": None,
                        "net_in_kb": round(net_delta[0], 2),
                        "net_out_kb": round(net_delta[1], 2),
                        "gpu_util_pct": None,
                        "gpu_vram_used_mb": None,
                        "gpu_power_w": None,
                        "sample_interval_s": interval,
                    })

                # GPU row
                if gpu_data:
                    rows.append({
                        "ts": now,
                        "grp": "gpu",
                        "cpu_pct": None,
                        "mem_rss_mb": None,
                        "net_in_kb": None,
                        "net_out_kb": None,
                        "gpu_util_pct": gpu_data["gpu_util_pct"],
                        "gpu_vram_used_mb": gpu_data["gpu_vram_used_mb"],
                        "gpu_power_w": gpu_data["gpu_power_w"],
                        "sample_interval_s": interval,
                    })

                insert_metrics(conn, rows)
                last_write_ts = now

        except Exception as e:
            log.error("Fast loop error: %s", e)

        # Sleep for remainder of interval
        elapsed = time.monotonic() - loop_start
        sleep_time = max(0, FAST_LOOP_INTERVAL - elapsed)
        if sleep_time > 0:
            time.sleep(sleep_time)

    # Cleanup
    log.info("Shutting down")
    close_gpu()
    conn.close()
    log.info("Goodbye")


if __name__ == "__main__":
    main()
