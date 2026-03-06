"""Tests for db.py — Group 1 (§1.5)."""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_open_db_creates_directory_and_sets_wal(tmp_path, monkeypatch):
    import config
    db_path = str(tmp_path / "sub" / "dir" / "test.db")
    monkeypatch.setattr(config, "DB_PATH", db_path)
    from db import open_db
    conn = open_db()
    assert os.path.isdir(os.path.dirname(db_path))
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    conn.close()


def test_open_db_sets_busy_timeout(tmp_path, monkeypatch):
    import config
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(config, "DB_PATH", db_path)
    from db import open_db
    conn = open_db()
    timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout == 5000
    conn.close()


def test_init_schema_creates_all_tables(test_db):
    cur = test_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = {row[0] for row in cur.fetchall()}
    expected = {
        "metrics", "collector_status", "metrics_daily",
        "disk_snapshots", "process_registry", "token_events", "tags",
    }
    assert expected.issubset(tables), f"Missing tables: {expected - tables}"


def test_init_collector_status_inserts_row(test_db):
    from db import init_collector_status
    init_collector_status(test_db)
    row = test_db.execute("SELECT id, last_seen, started_at FROM collector_status WHERE id = 1").fetchone()
    assert row is not None
    assert row[0] == 1
    assert row[1] > 0  # last_seen is a unix timestamp
    assert row[2] > 0  # started_at is a unix timestamp


def test_update_collector_status_updates_last_seen(test_db):
    from db import init_collector_status, update_collector_status
    init_collector_status(test_db)
    old = test_db.execute("SELECT last_seen FROM collector_status WHERE id = 1").fetchone()[0]
    time.sleep(1.1)
    update_collector_status(test_db)
    new = test_db.execute("SELECT last_seen FROM collector_status WHERE id = 1").fetchone()[0]
    assert new >= old


def test_insert_metrics_multiple_rows(test_db):
    from db import insert_metrics
    now = int(time.time())
    rows = [
        {"ts": now, "grp": "core", "cpu_pct": 10.5, "mem_rss_mb": 100.0,
         "net_in_kb": None, "net_out_kb": None, "gpu_util_pct": None,
         "gpu_vram_used_mb": None, "gpu_power_w": None, "sample_interval_s": 1},
        {"ts": now, "grp": "browser", "cpu_pct": 5.0, "mem_rss_mb": 200.0,
         "net_in_kb": None, "net_out_kb": None, "gpu_util_pct": None,
         "gpu_vram_used_mb": None, "gpu_power_w": None, "sample_interval_s": 1},
    ]
    insert_metrics(test_db, rows)
    count = test_db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    assert count == 2


def test_insert_metrics_empty_list_noop(test_db):
    from db import insert_metrics
    before = test_db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    insert_metrics(test_db, [])
    after = test_db.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    assert after == before


def test_insert_disk_snapshot(test_db):
    from db import insert_disk_snapshot
    now = int(time.time())
    insert_disk_snapshot(test_db, now, "test-dir", 1024, 10, 5.5)
    row = test_db.execute("SELECT ts, dir_key, size_bytes, file_count, journald_mb FROM disk_snapshots").fetchone()
    assert row == (now, "test-dir", 1024, 10, 5.5)


def test_register_and_unregister_process(test_db):
    from db import register_process, unregister_process, get_active_processes
    register_process(test_db, 1234, "test-proc", "openclaw-core", "desc")
    active = get_active_processes(test_db)
    assert len(active) == 1
    assert active[0][1] == 1234  # pid
    assert active[0][2] == "test-proc"  # name

    row_id = active[0][0]
    unregister_process(test_db, row_id)
    active = get_active_processes(test_db)
    assert len(active) == 0


def test_get_active_processes_excludes_unregistered(test_db):
    from db import register_process, unregister_process, get_active_processes
    register_process(test_db, 100, "proc-a", "core")
    register_process(test_db, 200, "proc-b", "browser")
    active = get_active_processes(test_db)
    assert len(active) == 2

    row_id = active[0][0]
    unregister_process(test_db, row_id)
    active = get_active_processes(test_db)
    assert len(active) == 1


def test_run_daily_aggregation_aggregates_and_prunes(test_db, monkeypatch):
    from db import insert_metrics, run_daily_aggregation
    import config

    # Insert metrics from "yesterday" (approx 1.5 days ago to be within the window)
    ts_yesterday = int(time.time()) - 86400 - 3600  # ~25 hours ago
    rows = [
        {"ts": ts_yesterday, "grp": "core", "cpu_pct": 20.0, "mem_rss_mb": 100.0,
         "net_in_kb": 10.0, "net_out_kb": 5.0, "gpu_util_pct": None,
         "gpu_vram_used_mb": None, "gpu_power_w": None, "sample_interval_s": 1},
        {"ts": ts_yesterday + 60, "grp": "core", "cpu_pct": 30.0, "mem_rss_mb": 150.0,
         "net_in_kb": 20.0, "net_out_kb": 10.0, "gpu_util_pct": None,
         "gpu_vram_used_mb": None, "gpu_power_w": None, "sample_interval_s": 1},
    ]
    insert_metrics(test_db, rows)

    run_daily_aggregation(test_db)

    daily = test_db.execute("SELECT * FROM metrics_daily").fetchall()
    assert len(daily) == 1
    # avg_cpu_pct should be 25.0
    assert daily[0][3] == 25.0  # avg_cpu_pct
    assert daily[0][4] == 30.0  # max_cpu_pct


def test_run_daily_aggregation_day_boundary(test_db, monkeypatch):
    from db import insert_metrics, run_daily_aggregation

    # The aggregation window is ts_start = now - 2*86400, ts_end = now - 86400
    # Use a distinct group to avoid interference
    now = int(time.time())
    ts_in_window = now - 86400 - 3600  # 25 hours ago (within window)
    ts_outside_window = now - 5 * 86400  # 5 days ago (well outside window)

    rows_in = [
        {"ts": ts_in_window, "grp": "boundary-test", "cpu_pct": 50.0, "mem_rss_mb": 100.0,
         "net_in_kb": None, "net_out_kb": None, "gpu_util_pct": None,
         "gpu_vram_used_mb": None, "gpu_power_w": None, "sample_interval_s": 1},
    ]
    rows_out = [
        {"ts": ts_outside_window, "grp": "boundary-test", "cpu_pct": 99.0, "mem_rss_mb": 500.0,
         "net_in_kb": None, "net_out_kb": None, "gpu_util_pct": None,
         "gpu_vram_used_mb": None, "gpu_power_w": None, "sample_interval_s": 1},
    ]
    insert_metrics(test_db, rows_in + rows_out)

    run_daily_aggregation(test_db)

    daily = test_db.execute(
        "SELECT avg_cpu_pct, max_cpu_pct FROM metrics_daily WHERE grp = 'boundary-test'"
    ).fetchall()
    assert len(daily) == 1
    # Only the in-window metric (50.0) should be aggregated, not the 99.0
    assert daily[0][0] == 50.0
    assert daily[0][1] == 50.0
