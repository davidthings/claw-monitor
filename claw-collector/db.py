"""SQLite helpers for claw-collector."""

import sqlite3
import time
import os
from config import DB_PATH


def open_db():
    """Open SQLite DB with WAL mode."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_schema(conn):
    """Create tables if they don't exist."""
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    if os.path.exists(schema_path):
        with open(schema_path) as f:
            conn.executescript(f.read())


def init_collector_status(conn):
    """Bootstrap collector_status single row."""
    now = int(time.time())
    conn.execute(
        "INSERT OR REPLACE INTO collector_status (id, last_seen, started_at) VALUES (1, ?, ?)",
        (now, now),
    )
    conn.commit()


def update_collector_status(conn):
    """Update last_seen timestamp."""
    now = int(time.time())
    conn.execute("UPDATE collector_status SET last_seen = ? WHERE id = 1", (now,))
    conn.commit()


def insert_metrics(conn, rows):
    """Insert metric rows. Each row is a dict with keys matching columns."""
    if not rows:
        return
    conn.executemany(
        """INSERT INTO metrics (ts, grp, cpu_pct, mem_rss_mb, net_in_kb, net_out_kb,
           gpu_util_pct, gpu_vram_used_mb, gpu_power_w, sample_interval_s)
           VALUES (:ts, :grp, :cpu_pct, :mem_rss_mb, :net_in_kb, :net_out_kb,
           :gpu_util_pct, :gpu_vram_used_mb, :gpu_power_w, :sample_interval_s)""",
        rows,
    )
    conn.commit()


def insert_disk_snapshot(conn, ts, dir_key, size_bytes, file_count, journald_mb=None):
    """Insert a disk snapshot row."""
    conn.execute(
        "INSERT INTO disk_snapshots (ts, dir_key, size_bytes, file_count, journald_mb) VALUES (?, ?, ?, ?, ?)",
        (ts, dir_key, size_bytes, file_count, journald_mb),
    )
    conn.commit()


def register_process(conn, pid, name, grp, description=None):
    """Register a new process."""
    now = int(time.time())
    conn.execute(
        "INSERT INTO process_registry (pid, name, grp, description, registered) VALUES (?, ?, ?, ?, ?)",
        (pid, name, grp, description, now),
    )
    conn.commit()


def unregister_process(conn, row_id):
    """Mark a process as unregistered."""
    now = int(time.time())
    conn.execute(
        "UPDATE process_registry SET unregistered = ? WHERE id = ?",
        (now, row_id),
    )
    conn.commit()


def get_active_processes(conn):
    """Get all active (not unregistered) processes."""
    cur = conn.execute(
        "SELECT id, pid, name, grp, description FROM process_registry WHERE unregistered IS NULL"
    )
    return cur.fetchall()


def run_daily_aggregation(conn):
    """Aggregate yesterday's metrics into metrics_daily and prune old data."""
    yesterday = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400))
    ts_start = int(time.time()) - 86400 * 2  # day before yesterday start
    ts_end = int(time.time()) - 86400  # yesterday end (approx)

    conn.execute(
        """INSERT OR IGNORE INTO metrics_daily
           (date, grp, avg_cpu_pct, max_cpu_pct, avg_mem_rss_mb, max_mem_rss_mb,
            sum_net_in_kb, sum_net_out_kb, avg_gpu_pct, max_gpu_pct, max_vram_mb)
           SELECT ?, grp,
             AVG(cpu_pct), MAX(cpu_pct), AVG(mem_rss_mb), MAX(mem_rss_mb),
             SUM(net_in_kb), SUM(net_out_kb), AVG(gpu_util_pct), MAX(gpu_util_pct),
             MAX(gpu_vram_used_mb)
           FROM metrics WHERE ts >= ? AND ts < ?
           GROUP BY grp""",
        (yesterday, ts_start, ts_end),
    )

    # Prune old metrics
    from config import RETENTION_DAYS
    cutoff = int(time.time()) - RETENTION_DAYS * 86400
    conn.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,))
    conn.commit()
