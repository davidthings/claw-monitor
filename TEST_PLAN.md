# Claw-Monitor Test Plan

Comprehensive test plan covering the Python collector daemon, Next.js API routes, and end-to-end integration tests against the live system.

---

## 1. Unit Tests — Python Collector (`claw-collector/`)

**Framework:** pytest
**Location:** `claw-collector/tests/`
**Run command:** `cd claw-collector && python -m pytest tests/ -v`

### 1.1 `pid_tracker.py`

#### `test_read_proc_cmdline_returns_decoded_string`
- Write a fake `/proc/<pid>/cmdline` with null-separated args to a temp file
- Monkeypatch `open()` to redirect `/proc/{pid}/cmdline` to the temp file
- Assert the returned string has spaces replacing nulls and is stripped
- **Mocks:** filesystem (monkeypatch `builtins.open`)

#### `test_read_proc_cmdline_missing_pid_returns_empty`
- Call `read_proc_cmdline(999999)` (non-existent PID)
- Assert returns `""`

#### `test_read_proc_comm_returns_stripped_name`
- Create temp file with `"python3\n"`
- Monkeypatch open for `/proc/{pid}/comm`
- Assert returns `"python3"`

#### `test_read_proc_stat_returns_utime_stime`
- Create temp file with a realistic `/proc/<pid>/stat` line (26+ space-separated fields)
- Monkeypatch open, assert returns `(int(field[13]), int(field[14]))`
- Verify the correct 0-indexed fields are extracted

#### `test_read_proc_stat_missing_pid_returns_none_none`
- Call with non-existent PID
- Assert returns `(None, None)`

#### `test_read_proc_rss_parses_vmrss_in_mb`
- Create temp `/proc/<pid>/status` with `VmRSS: 102400 kB`
- Assert returns `100.0` (102400 / 1024)

#### `test_read_proc_rss_missing_pid_returns_none`
- Non-existent PID, assert returns `None`

#### `test_get_children_parses_children_file`
- Create temp file for `/proc/{pid}/task/{pid}/children` with content `"1234 5678 "`
- Assert returns `[1234, 5678]`

#### `test_get_children_no_children_returns_empty`
- Empty children file, assert returns `[]`

#### `test_get_all_descendants_walks_tree`
- Monkeypatch `get_children` to return a known tree:
  - PID 100 -> children [200, 300]
  - PID 200 -> children [400]
  - PID 300 -> children []
  - PID 400 -> children []
- Call `get_all_descendants(100)`
- Assert returns `[(200, 1), (300, 1), (400, 2)]` (order may vary by BFS)
- Verify depth values are correct

#### `test_find_gateway_pid_finds_matching_process`
- Monkeypatch `os.listdir("/proc")` to return `["1", "42", "abc", "100"]`
- Monkeypatch `read_proc_cmdline` to return `"openclaw-gateway --port 8080"` for PID 42
- Assert returns `42`

#### `test_find_gateway_pid_returns_none_when_absent`
- Monkeypatch `os.listdir` to return numeric entries
- All `read_proc_cmdline` calls return non-matching strings
- Assert returns `None`

#### `test_classify_process_gateway_is_core`
- `classify_process(pid=100, gateway_pid=100, depth=0)` -> `"openclaw-core"`

#### `test_classify_process_direct_child_chrome_is_browser`
- Monkeypatch `read_proc_cmdline` to return a string containing `"chrome"`
- `classify_process(pid=200, gateway_pid=100, depth=1)` -> `"openclaw-browser"`

#### `test_classify_process_direct_child_non_chrome_is_core`
- cmdline = `"node server.js"`
- depth=1 -> `"openclaw-core"`

#### `test_classify_process_grandchild_chrome_is_browser`
- cmdline contains `"chromium"`, depth=2 -> `"openclaw-browser"`

#### `test_classify_process_grandchild_non_chrome_is_agent`
- cmdline = `"python3 agent.py"`, depth=2 -> `"openclaw-agent"`

#### `test_discover_processes_returns_gateway_and_descendants`
- Monkeypatch `get_all_descendants` to return known tree
- Monkeypatch `read_proc_comm` and `classify_process`
- Assert the result list includes the gateway as `"openclaw-core"` plus classified descendants

#### `test_discover_processes_no_gateway_returns_empty`
- `discover_processes(None)` -> `[]`

#### `test_verify_pid_valid_process`
- Monkeypatch `os.path.exists("/proc/{pid}")` -> True
- Monkeypatch `read_proc_comm` -> `"python3"`
- `verify_pid(pid, "python3")` -> `True`

#### `test_verify_pid_comm_mismatch_detects_reuse`
- `/proc/{pid}` exists but comm returns `"bash"` instead of expected `"python3"`
- `verify_pid(pid, "python3")` -> `False`

#### `test_verify_pid_gone_process`
- `/proc/{pid}` does not exist
- `verify_pid(pid, "python3")` -> `False`

### 1.2 `net_tracker.py`

#### `test_get_delta_first_call_returns_none`
- Create a `NetTracker`, monkeypatch `read_net_dev` to return `(1000, 2000)`
- First `get_delta()` returns `None`

#### `test_get_delta_second_call_returns_kb_diff`
- First call: `read_net_dev` returns `(1024000, 2048000)`
- Second call: returns `(2048000, 3072000)`
- `get_delta()` should return `(1000.0, 1000.0)` (delta bytes / 1024)

#### `test_get_delta_counter_wrap_clamps_to_zero`
- First call: returns `(5000, 5000)`
- Second call: returns `(3000, 3000)` (counter reset/wrap)
- Delta should clamp to `(0.0, 0.0)` via `max(0, ...)`

#### `test_read_net_dev_excludes_loopback`
- Monkeypatch `/proc/net/dev` contents with `lo` and `eth0` entries
- Assert `lo` bytes are excluded from totals, only `eth0` counted

#### `test_read_net_dev_parses_multiple_interfaces`
- Provide `eth0` and `wlan0` entries
- Assert both rx and tx are summed

#### `test_read_net_dev_skips_header_lines`
- Include the two standard header lines (`Inter-| ...` and `face |...`)
- Assert they don't cause parsing errors

#### `test_read_net_dev_missing_file_returns_zeros`
- Monkeypatch open to raise `FileNotFoundError`
- Returns `(0, 0)`

### 1.3 `gpu_tracker.py`

#### `test_init_gpu_success`
- Mock `pynvml.nvmlInit`, `nvmlDeviceGetHandleByIndex`, `nvmlDeviceGetName`
- Assert `init_gpu()` returns `True`
- Assert module-level `_nvml_available` is `True`

#### `test_init_gpu_no_nvidia_returns_false`
- Mock `pynvml.nvmlInit` to raise `Exception("No NVIDIA driver")`
- Assert `init_gpu()` returns `False`

#### `test_read_gpu_returns_dict`
- Mock pynvml functions:
  - `nvmlDeviceGetUtilizationRates` -> mock with `.gpu = 45`
  - `nvmlDeviceGetMemoryInfo` -> mock with `.used = 4 * 1024 * 1024 * 1024`
  - `nvmlDeviceGetPowerUsage` -> `150000` (mW)
- Assert returns `{"gpu_util_pct": 45.0, "gpu_vram_used_mb": 4096.0, "gpu_power_w": 150.0}`

#### `test_read_gpu_power_error_returns_none_power`
- Mock `nvmlDeviceGetPowerUsage` to raise Exception
- Assert returned dict has `gpu_power_w: None` but other fields present

#### `test_read_gpu_when_unavailable_returns_none`
- With `_nvml_available = False`, assert `read_gpu()` returns `None`

#### `test_close_gpu_calls_shutdown`
- Mock `pynvml.nvmlShutdown`
- Call `close_gpu()`, assert shutdown was called
- Assert `_nvml_available` is `False` after

**Mock strategy:** All pynvml calls are mocked via `unittest.mock.patch`. The `pynvml` import is inside the functions, so mock `pynvml.nvmlInit` etc. at the module path. On CI without GPU, all tests pass because pynvml is never called for real.

### 1.4 `disk_tracker.py`

#### `test_scan_directory_counts_files_and_bytes`
- Create a temp directory with 3 files of known sizes (e.g., 100, 200, 300 bytes)
- Assert `scan_directory(tmpdir)` returns `(600, 3)`

#### `test_scan_directory_recursive`
- Create nested subdirectories with files
- Assert all files in all subdirs are counted

#### `test_scan_directory_nonexistent_returns_zeros`
- `scan_directory("/nonexistent/path")` -> `(0, 0)`

#### `test_scan_directory_permission_error_partial`
- Create a directory with one accessible and one unreadable file (chmod 000)
- Assert the accessible file is still counted (graceful degradation)

#### `test_get_journald_size_parses_megabytes`
- Mock `subprocess.run` to return stdout `"Archived and active journals take up 24.5M in the file system."`
- Assert returns `24.5`

#### `test_get_journald_size_parses_gigabytes`
- stdout = `"... take up 1.2G ..."`
- Assert returns `1228.8` (1.2 * 1024)

#### `test_get_journald_size_error_returns_none`
- Mock `subprocess.run` to raise `subprocess.TimeoutExpired`
- Assert returns `None`

### 1.5 `db.py`

#### `test_open_db_creates_directory_and_sets_wal`
- Use a temp path, monkeypatch `DB_PATH`
- Call `open_db()`, assert the parent directory was created
- Execute `PRAGMA journal_mode` and assert result is `"wal"`

#### `test_open_db_sets_busy_timeout`
- After `open_db()`, query `PRAGMA busy_timeout` -> `5000`

#### `test_init_schema_creates_all_tables`
- Open a temp DB, call `init_schema(conn)`
- Query `sqlite_master` for table names
- Assert all 7 tables exist: `metrics`, `collector_status`, `metrics_daily`, `disk_snapshots`, `process_registry`, `token_events`, `tags`

#### `test_init_collector_status_inserts_row`
- Call `init_collector_status(conn)`
- Query `collector_status`, assert exactly 1 row with `id=1`
- Assert `last_seen` and `started_at` are recent timestamps

#### `test_update_collector_status_updates_last_seen`
- Init status, sleep 1s (or mock time), call `update_collector_status(conn)`
- Assert `last_seen` is updated to a newer timestamp

#### `test_insert_metrics_multiple_rows`
- Insert 3 metric rows with different grp values
- Query `metrics` table, assert 3 rows with correct data

#### `test_insert_metrics_empty_list_noop`
- `insert_metrics(conn, [])` — no exception, no rows inserted

#### `test_insert_disk_snapshot`
- Insert a snapshot with `journald_mb=24.5`
- Query and assert all fields match

#### `test_register_and_unregister_process`
- `register_process(conn, 1234, "python3", "openclaw-agent")`
- Assert row in `process_registry` with `unregistered IS NULL`
- Get `row_id`, call `unregister_process(conn, row_id)`
- Assert `unregistered` is now set

#### `test_get_active_processes_excludes_unregistered`
- Register 3 processes, unregister 1
- `get_active_processes(conn)` returns 2 rows

#### `test_run_daily_aggregation_aggregates_and_prunes`
- Insert metrics with timestamps from "yesterday"
- Call `run_daily_aggregation(conn)`
- Assert `metrics_daily` has aggregated rows
- Insert metrics with timestamps older than `RETENTION_DAYS`
- Call again, assert old metrics are deleted from `metrics`

### 1.6 `collector.py` — `CpuTracker` class

#### `test_cpu_tracker_first_call_returns_none`
- Monkeypatch `read_proc_stat` to return `(1000, 500)`
- `CpuTracker().get_cpu_pct(42)` -> `None` (first call seeds state)

#### `test_cpu_tracker_second_call_returns_percentage`
- First call: stat returns `(1000, 500)`, record time
- Second call (after ~0.1s): stat returns `(1100, 600)` (200 ticks delta)
- CPU% = (200 / CLK_TCK) / dt * 100
- Assert result is approximately correct (within 10% tolerance due to timing)

#### `test_cpu_tracker_remove_pid_clears_state`
- Seed a PID, call `remove_pid(pid)`
- Next `get_cpu_pct(pid)` returns `None` again (fresh start)

#### `test_cpu_tracker_process_gone_returns_none`
- Monkeypatch `read_proc_stat` to return `(None, None)` (process died)
- Assert returns `None`

### 1.7 `collector.py` — `sync_processes()`

#### `test_sync_processes_registers_new_pids`
- Mock `discover_processes` to return 2 new PIDs
- Mock `get_active_processes` to return empty
- Assert `register_process` called twice
- Assert returned `known_pids` dict contains both PIDs

#### `test_sync_processes_unregisters_gone_pids`
- `get_active_processes` returns a PID that `verify_pid` says is gone
- Assert `unregister_process` is called for that PID

#### `test_sync_processes_detects_comm_mismatch`
- DB has PID 100 with name `"python3"`, but `verify_pid(100, "python3")` returns `False` (comm now `"bash"`)
- Assert the process is unregistered (PID reuse detected)

### 1.8 `collector.py` — Write-gate logic

#### `test_fast_loop_skips_write_when_below_threshold`
- Mock all PID CPU readings to return 0.5% (below `ACTIVITY_THRESHOLD_PCT = 1.0`)
- Assert `insert_metrics` is NOT called

#### `test_fast_loop_writes_when_above_threshold`
- Mock one PID CPU reading to return 5.0%
- Assert `insert_metrics` IS called with correctly structured rows

#### `test_fast_loop_includes_net_and_gpu_rows`
- CPU active, mock net_delta to return `(10.0, 20.0)`, mock GPU data
- Assert inserted rows include grp `"net"` and grp `"gpu"` entries

---

## 2. Unit Tests — Next.js API Routes (`web/src/app/api/`)

**Framework:** Vitest
**Location:** `web/tests/`
**Run command:** `cd web && npx vitest run`

**Mock strategy for all API tests:** Mock `@/lib/db` with an in-memory better-sqlite3 instance initialized from `schema.sql`. Each test gets a fresh database.

### 2.1 `POST /api/tags`

#### `test_tags_post_minimal_valid`
- Body: `{category: "coding", text: "fixing bug", source: "clawbot"}`
- Assert: 201, `ok: true`, row in `tags` table with `ts ~ now`, `recorded_at ~ now`

#### `test_tags_post_missing_category_returns_400`
- Body: `{text: "hi", source: "clawbot"}`
- Assert: 400, error message mentions "category"

#### `test_tags_post_missing_text_returns_400`
- Body: `{category: "coding", source: "clawbot"}`
- Assert: 400

#### `test_tags_post_missing_source_returns_400`
- Body: `{category: "coding", text: "hi"}`
- Assert: 400

#### `test_tags_post_invalid_category_returns_400`
- Body: `{category: "invalid_cat", text: "hi", source: "clawbot"}`
- Assert: 400, error lists valid categories

#### `test_tags_post_invalid_source_returns_400`
- Body: `{category: "coding", text: "hi", source: "unknown_source"}`
- Assert: 400

#### `test_tags_post_backdate_unix_timestamp`
- Body: `{..., ts: 1741200000}`
- Assert: DB row has `ts = 1741200000`, `recorded_at` is close to current time
- **Concerns:** The hardcoded timestamp `1741200000` is arbitrary but fine for a unit test. If the `resolveTs()` implementation rejects timestamps far in the past or future, this value may need to be adjusted to be within an acceptable range.

#### `test_tags_post_backdate_relative_minutes`
- Body: `{..., ts: "-10m"}`
- Assert: DB `ts` is approximately `now - 600` (within 2s tolerance)

#### `test_tags_post_backdate_relative_seconds`
- Body: `{..., ts: "-30s"}`
- Assert: DB `ts ~ now - 30`

#### `test_tags_post_backdate_relative_hours`
- Body: `{..., ts: "-2h"}`
- Assert: DB `ts ~ now - 7200`

#### `test_tags_post_backdate_natural_language`
- Body: `{..., ts: "10 minutes ago"}`
- Assert: DB `ts ~ now - 600`

#### `test_tags_post_backdate_iso8601`
- Body: `{..., ts: "2026-03-06T08:00:00Z"}`
- Assert: DB `ts` equals the parsed ISO timestamp

#### `test_tags_post_unparseable_ts_returns_400`
- Body: `{..., ts: "not-a-date"}`
- Assert: 400, error mentions "Cannot parse ts"

#### `test_tags_post_ts_null_uses_now`
- Body: `{..., ts: null}`
- Assert: DB `ts ~ now`

#### `test_tags_post_ts_omitted_uses_now`
- Body without `ts` field
- Assert: DB `ts ~ now`, `recorded_at ~ now`, and `ts == recorded_at` (within 1s)

#### `test_tags_post_with_session_id`
- Body includes `session_id: "abc-123"`
- Assert: DB row has `session_id = "abc-123"`

### 2.2 `GET /api/tags`

#### `test_tags_get_returns_all_in_range`
- Insert 5 tags spanning a time range
- GET with `from` and `to` covering all 5
- Assert: 5 tags returned, ordered by `ts DESC`

#### `test_tags_get_category_filter`
- Insert tags with categories `"coding"` and `"research"`
- GET with `category=coding`
- Assert: only coding tags returned

#### `test_tags_get_source_filter`
- Insert tags with sources `"clawbot"` and `"user"`
- GET with `source=clawbot`
- Assert: only clawbot tags

#### `test_tags_get_max_500_rows`
- Insert 600 tags
- Assert: response contains exactly 500
- **Concerns:** Inserting 600 rows is slow in a loop; use a single multi-row INSERT or a transaction for speed. If the limit changes from 500, this test breaks — consider reading the limit from a constant.

#### `test_tags_get_includes_recorded_at`
- Insert a tag, GET it back
- Assert: response object includes `recorded_at` field

### 2.3 `POST /api/tokens`

#### `test_tokens_post_valid`
- Body: `{tool: "claude-code", model: "claude-sonnet-4-6", tokens_in: 1000, tokens_out: 500}`
- Assert: 201, `ok: true`, row in `token_events`

#### `test_tokens_post_minimal_fields`
- Body: `{tool: "test", model: "gpt-4o-mini"}` (no tokens_in/out/session_id)
- Assert: 201, DB row has `tokens_in=0, tokens_out=0, session_id=NULL`

#### `test_tokens_post_with_session_id`
- Body includes `session_id: "sess-42"`
- Assert: DB row has `session_id = "sess-42"`

#### `test_tokens_post_missing_tool_returns_400`
- Body: `{model: "gpt-4"}`
- Assert: 400

#### `test_tokens_post_missing_model_returns_400`
- Body: `{tool: "test"}`
- Assert: 400

### 2.4 `GET /api/metrics`

#### `test_metrics_get_requires_from_param`
- GET `/api/metrics` without `from`
- Assert: 400

#### `test_metrics_get_raw_resolution`
- Insert 10 metric rows in last hour
- GET with `from=now-3600, resolution=raw`
- Assert: `resolution: "raw"`, 10 rows returned

#### `test_metrics_get_auto_resolution_short_range`
- Range < 6h -> resolution should be `"raw"`

#### `test_metrics_get_auto_resolution_medium_range`
- Range 6h-3d -> resolution should be `"hourly"`

#### `test_metrics_get_auto_resolution_long_range`
- Range > 3d -> resolution should be `"daily"`, queries `metrics_daily`

#### `test_metrics_get_group_filter`
- Insert rows for grp `"openclaw-core"` and `"openclaw-browser"`
- GET with `group=openclaw-core`
- Assert: only core rows returned

#### `test_metrics_get_hourly_aggregation`
- Insert 60 rows across 1 hour
- GET with `resolution=hourly`
- Assert: 1 aggregated row with AVG(cpu_pct), SUM(net_in_kb)

#### `test_metrics_get_raw_limit_10000`
- Insert 15000 rows
- GET with `resolution=raw`
- Assert: exactly 10000 rows returned
- **Concerns:** Inserting 15000 rows is expensive; use a transaction-wrapped bulk insert. This test and `test_tags_get_max_500_rows` / `test_disk_get_max_5000_rows` / `test_registry_get_max_200_rows` all test row limits — if limits are configurable constants, tests should reference them.

#### `test_metrics_get_sparse_data_gaps`
- Insert rows at ts=100 and ts=500 (400s gap)
- Assert: both rows returned, no synthetic fill rows

### 2.5 `GET /api/metrics/stream` (SSE)

#### `test_stream_returns_event_stream_content_type`
- GET `/api/metrics/stream`
- Assert: `Content-Type: text/event-stream`
- Assert: `Cache-Control: no-cache`

#### `test_stream_sends_ping_every_30s`
- Connect to SSE, wait ~31s (or mock the interval timer)
- Assert: received at least one `: ping\n\n` frame
- **Concerns:** A 31s real-time wait is slow for CI. Prefer mocking `setInterval` / the ping timer to fire immediately. If the ping interval is configurable, use a short interval for tests.

#### `test_stream_sends_data_on_new_metrics`
- Connect SSE, then insert a metric row into DB with ts > connection start
- Assert: received a `data: {...}\n\n` event containing the metric

#### `test_stream_groups_by_timestamp`
- Insert 3 rows with same ts but different grps (`openclaw-core`, `net`, `gpu`)
- Assert: single SSE event with `groups`, `net`, and `gpu` sub-objects

**Note:** SSE tests require either a real HTTP server (use Next.js test server or `node --experimental-vm-modules`) or a mock of the `ReadableStream` controller. Recommend using Playwright or a lightweight HTTP client for these.

**Implementation assumption:** These tests assume the `/api/metrics/stream` route polls the DB at a fixed interval (e.g. every 1–2s) and emits new rows as SSE events. Before implementing SSE tests, verify the route implementation — if it uses a push mechanism (e.g. SQLite update hook, file watcher, or IPC from the collector) instead of polling, the test approach changes significantly. In particular:
- `test_stream_sends_data_on_new_metrics` and `test_stream_groups_by_timestamp` depend on the polling assumption — a push-based route would require triggering the push mechanism rather than simply inserting a DB row.
- `test_stream_sends_ping_every_30s` is unaffected (ping is a timer regardless of data delivery mechanism).

### 2.6 `GET /api/disk`

#### `test_disk_get_default_range_last_24h`
- Insert snapshots at various times
- GET `/api/disk` with no params
- Assert: only snapshots from last 24h returned

#### `test_disk_get_custom_range`
- GET with `from` and `to`
- Assert: only rows in range returned

#### `test_disk_get_dir_key_filter`
- Insert rows for `"openclaw-workspace"` and `"monitor-db"`
- GET with `dir_key=monitor-db`
- Assert: only `monitor-db` rows

#### `test_disk_get_max_5000_rows`
- Insert 6000 rows
- Assert: response capped at 5000

#### `test_disk_get_order_desc`
- Assert: rows ordered by `ts DESC`

### 2.7 `GET /api/tokens/summary`

#### `test_tokens_summary_group_by_tool`
- Insert events for tools `"claude-code"` and `"aider"`
- GET with `group_by=tool`
- Assert: 2 summary rows, each with correct `total_in`, `total_out`, `call_count`

#### `test_tokens_summary_group_by_model`
- GET with `group_by=model`
- Assert: grouped by model name

#### `test_tokens_summary_group_by_session`
- GET with `group_by=session_id`
- Assert: grouped by session_id

#### `test_tokens_summary_invalid_group_by_defaults_to_tool`
- GET with `group_by=invalid`
- Assert: defaults to grouping by `tool`

#### `test_tokens_summary_cost_calculation`
- Insert event: model=`"claude-sonnet-4-6"`, tokens_in=1000000, tokens_out=1000000
- Expected cost: 1M * $3/Mtok + 1M * $15/Mtok = $18.00
- Assert: `est_cost_usd` is `18.00`
- **Concerns:** This test duplicates pricing knowledge from `pricing.json`. If pricing changes, both the test and `pricing.json` must be updated. Consider importing `pricing.json` in the test to compute the expected value dynamically (see also `cost.test.ts` section 2.10).

#### `test_tokens_summary_unknown_model_zero_cost`
- Insert event with model=`"unknown-model"`
- Assert: `est_cost_usd` is `0`

#### `test_tokens_summary_totals`
- Insert multiple events
- Assert: `totals.tokens_in` = sum of all, `totals.calls` = count of all, `totals.est_cost_usd` rounded to 2 decimals

### 2.8 `POST /api/registry/process`

#### `test_registry_post_valid`
- Body: `{pid: 1234, name: "python3", group: "openclaw-agent"}`
- Assert: 201, row in `process_registry`

#### `test_registry_post_with_description`
- Body includes `description: "main agent process"`
- Assert: DB row has description field set

#### `test_registry_post_missing_pid_returns_400`
- Body: `{name: "python3", group: "agent"}`
- Assert: 400

#### `test_registry_post_missing_name_returns_400`
- Body: `{pid: 1234, group: "agent"}`
- Assert: 400

#### `test_registry_post_missing_group_returns_400`
- Body: `{pid: 1234, name: "python3"}`
- Assert: 400

#### `test_registry_post_duplicate_pid_inserts_second_row`
- POST the same PID twice
- Assert: 2 rows in `process_registry` (the schema allows duplicate PIDs for tracking re-registrations)

### 2.9 `GET /api/registry`

#### `test_registry_get_returns_processes`
- Insert 3 processes
- GET `/api/registry`
- Assert: `processes` array with 3 items, ordered by `registered DESC`

#### `test_registry_get_max_200_rows`
- Insert 250 processes
- Assert: response capped at 200

#### `test_registry_get_includes_unregistered`
- Insert process, set `unregistered` timestamp
- Assert: response includes it with `unregistered` field set

### 2.10 `cost.ts` — Unit Tests (`web/src/lib/cost.ts`)

Standalone unit tests for the cost computation helper. These test `estimateCost()` in isolation, separate from the `/api/tokens/summary` route tests (which test cost as part of the full API response).

#### `test_estimate_cost_known_model`
- `estimateCost("claude-sonnet-4-6", 1_000_000, 1_000_000)`
- Expected: `1 * 3.00 + 1 * 15.00 = 18.00`
- Assert: returns `18.00`

#### `test_estimate_cost_unknown_model_returns_zero`
- `estimateCost("unknown-model", 500_000, 500_000)`
- Assert: returns `0`

#### `test_estimate_cost_zero_tokens`
- `estimateCost("claude-sonnet-4-6", 0, 0)`
- Assert: returns `0`

#### `test_estimate_cost_input_only`
- `estimateCost("claude-sonnet-4-6", 1_000_000, 0)`
- Assert: returns `3.00`

#### `test_estimate_cost_output_only`
- `estimateCost("claude-sonnet-4-6", 0, 1_000_000)`
- Assert: returns `15.00`

#### `test_estimate_cost_fractional_tokens`
- `estimateCost("claude-sonnet-4-6", 500, 1000)`
- Expected: `(500/1e6)*3 + (1000/1e6)*15 = 0.0015 + 0.015 = 0.0165`
- Assert: returns `0.0165` (no rounding — rounding is the caller's responsibility)

#### `test_estimate_cost_all_pricing_models`
- Loop over every key in `pricing.json`
- For each model: call `estimateCost(model, 1_000_000, 1_000_000)` and assert result equals `input_per_mtok + output_per_mtok`
- Ensures pricing.json stays in sync with what the function reads

#### `test_estimate_cost_empty_string_model`
- `estimateCost("", 1000, 1000)`
- Assert: returns `0` (empty string is not a known model)

**Concerns:**
- `pricing.json` is imported at module load time. If tests modify or mock `pricing.json`, ensure the mock is set before the module is imported (Vitest `vi.mock()` hoisting handles this). Alternatively, test against the real `pricing.json` and update tests when pricing changes.

### 2.11 `middleware.ts`

#### `test_middleware_allows_localhost_ipv4`
- Request with `x-forwarded-for: 127.0.0.1`
- Assert: `NextResponse.next()` (pass-through)

#### `test_middleware_allows_localhost_ipv6`
- Request with `x-forwarded-for: ::1`
- Assert: pass-through

#### `test_middleware_allows_tailscale_cgnat`
- IPs to test: `100.64.0.1`, `100.100.50.25`, `100.127.255.255`
- All should pass through

#### `test_middleware_rejects_tailscale_boundary_below`
- IP: `100.63.255.255` (just below CGNAT range)
- Assert: 403 Forbidden

#### `test_middleware_rejects_tailscale_boundary_above`
- IP: `100.128.0.0` (just above CGNAT range)
- Assert: 403 Forbidden

#### `test_middleware_rejects_public_ip`
- IP: `203.0.113.1`
- Assert: 403

#### `test_middleware_uses_first_forwarded_ip`
- `x-forwarded-for: 100.100.1.1, 203.0.113.1`
- Assert: allowed (uses first IP `100.100.1.1`)

#### `test_middleware_falls_back_to_x_real_ip`
- No `x-forwarded-for`, `x-real-ip: 100.100.1.1`
- Assert: allowed

#### `test_middleware_defaults_to_localhost_when_no_headers`
- No IP headers at all
- Assert: allowed (defaults to `127.0.0.1`)

---

## 3. Integration / Functional Tests — Real Data Collection

**Framework:** pytest (Python portions), Vitest + curl/fetch (API portions)
**Location:** `tests/integration/`
**Prerequisite:** Collector and web services must be running, or started by the test harness.
**Database:** Use a **separate test DB** (e.g., `~/.openclaw/claw-monitor/test-metrics.db`) configured via env var override.

### 3.1 Collector Against Real `/proc`

#### `test_collector_finds_openclaw_gateway_pid`
- Precondition: `openclaw-gateway` process is running
- Start collector (or call `find_gateway_pid()` directly)
- Assert: returns a valid PID that matches `pgrep openclaw-gateway`
- **Concerns:** Cannot be parallelised — depends on the real running process tree. Fails if `openclaw-gateway` is not running at test time. Mark as `@pytest.mark.requires_openclaw`.

#### `test_cpu_percent_matches_top`
- Read CPU% for the gateway PID via `CpuTracker` (2 readings, 1s apart)
- Compare with `ps -p <pid> -o %cpu` output
- Assert: values are within 20% of each other (accounting for measurement window differences)
- **Concerns:** `ps -o %cpu` reports lifetime average, not instantaneous — comparison with a 1s delta measurement is inherently noisy. Consider using `top -bn1 -p <pid>` for a more comparable snapshot. The 20% tolerance may still flake on lightly loaded systems; consider a wider tolerance or making this a manual-only test.

#### `test_write_gate_idle_no_rows`
- Ensure OpenClaw is idle (no active sessions)
- Run the fast loop for 10 iterations
- Assert: zero rows written to `metrics` table during the period
- Assert: `collector_status.last_seen` DID update (via slow loop)

#### `test_write_gate_active_writes_rows`
- Trigger CPU activity on a monitored process (e.g., `stress --cpu 1 --timeout 3` as a registered process)
- Run fast loop for 5 iterations
- Assert: rows written to `metrics` with `cpu_pct > 1.0`

#### `test_collector_status_updated_every_60s`
- Record `collector_status.last_seen`
- Wait 65s (or run slow loop once)
- Assert: `last_seen` has advanced by ~60s

**Concerns:** Waiting 65s makes this test too slow for CI. Fast-test alternatives:
1. **Mock `time.sleep`** to fast-forward the slow loop (monkeypatch `time.sleep` to no-op; the loop body executes immediately).
2. **Use `SLOW_LOOP_INTERVAL` env override:** Set `CM_SLOW_LOOP_INTERVAL_S=1` so the slow loop fires every 1s. See §4 Test Infrastructure for the configurable constant prerequisite.
3. **Call the slow-loop function directly** (if extracted as a testable unit) instead of waiting for the loop timer.

#### `test_disk_snapshots_written_every_60s`
- Count rows in `disk_snapshots`
- Run slow loop once
- Assert: new rows inserted for each configured `DISK_DIRS` key (6 keys)

**Concerns:** Same 60s wait issue as `test_collector_status_updated_every_60s`. Use the same fast-test strategy (mock `time.sleep`, or set `CM_SLOW_LOOP_INTERVAL_S=1`, or call the slow-loop function directly).

#### `test_gpu_rows_only_when_active`
- If GPU available: verify GPU rows appear alongside other metric rows when activity gate is open
- If GPU unavailable: verify no GPU rows ever written (graceful skip)

#### `test_net_rows_written_when_active`
- When activity gate is open, verify `grp="net"` rows appear with `net_in_kb` and `net_out_kb` values

### 3.2 API Integration (against running web server)

#### `test_post_tag_and_read_back`
- POST to `http://localhost:${CM_PORT:-7432}/api/tags`:
  ```json
  {"category": "coding", "text": "integration test tag", "source": "system"}
  ```
- Assert: 201 response
- GET `/api/tags?from=<now-60>&to=<now>`
- Assert: the tag appears in the response with correct fields

#### `test_post_token_and_read_summary`
- POST to `/api/tokens`:
  ```json
  {"tool": "test-tool", "model": "claude-sonnet-4-6", "tokens_in": 500, "tokens_out": 100}
  ```
- Assert: 201
- GET `/api/tokens/summary?from=<now-60>&to=<now>&group_by=tool`
- Assert: summary includes `test-tool` with correct token counts

#### `test_sse_stream_receives_new_data`
- Connect an SSE client to `/api/metrics/stream`
- Wait for initial connection
- Insert a metric row directly into the DB (or trigger collector activity)
- Assert: SSE event received within 5s containing the new data

#### `test_sse_stream_ping_received`
- Connect SSE client
- Wait 35s
- Assert: at least one `: ping` comment frame received
- **Concerns:** 35s real-time wait. Same mitigation as `test_stream_sends_ping_every_30s` — mock the timer or use a configurable short ping interval for test runs.

### 3.3 End-to-End Script Tests

#### `test_tag_sh_creates_db_row`
- Run: `bash scripts/tag.sh coding "e2e test from tag.sh" system`
- Wait 2s (fire-and-forget curl)
- Query DB: assert row exists with `category="coding"`, `text="e2e test from tag.sh"`

#### `test_tag_sh_backdate`
- Run: `bash scripts/tag.sh coding "backdated tag" system "" "-10m"`
- Wait 2s
- Query DB: assert `ts` is approximately `now - 600` (within 10s tolerance)
- Assert: `recorded_at` is approximately `now`

#### `test_tag_sh_invalid_category_exits_gracefully`
- Run: `bash scripts/tag.sh invalid_cat "test" system`
- Assert: exit code 0 (fire-and-forget)
- Assert: stderr contains "Invalid category"

#### `test_register_tool_sh_creates_db_row`
- Run: `bash scripts/register-tool.sh $$ bash openclaw-test "test process"`
- Wait 2s
- GET `/api/registry`
- Assert: process with `name="bash"`, `grp="openclaw-test"` appears

#### `test_register_tool_sh_missing_args_exits_gracefully`
- Run: `bash scripts/register-tool.sh` (no args)
- Assert: exit code 0, stderr shows usage

### 3.4 Backdating Verification

#### `test_backdate_relative_minutes_db_check`
- POST `/api/tags` with `ts: "-10m"`
- Query DB directly
- Assert: `ts` is within 2s of `(now - 600)`
- Assert: `recorded_at` is within 2s of `now`
- Assert: `recorded_at - ts` is approximately 600

#### `test_backdate_natural_language_db_check`
- POST with `ts: "30 seconds ago"`
- Assert: `ts ~ now - 30`, `recorded_at ~ now`

#### `test_backdate_iso_db_check`
- POST with `ts: "2026-03-06T12:00:00Z"`
- Assert: `ts` equals `1741262400` (or whatever the exact epoch is)

---

## 4. Test Infrastructure

### 4.0 Configurable Constants for Fast Tests

**Prerequisite code change:** `claw-collector/config.py` must read loop intervals from environment variables so that tests can override them:

```python
SLOW_LOOP_INTERVAL = int(os.environ.get("CM_SLOW_LOOP_INTERVAL_S", "60"))
FAST_LOOP_INTERVAL = int(os.environ.get("CM_FAST_LOOP_INTERVAL_S", "1"))
```

This allows integration tests to set `CM_SLOW_LOOP_INTERVAL_S=1` to avoid 60s waits. The `collector.py` main loop must use `config.SLOW_LOOP_INTERVAL` (not a hardcoded `60`) for this to take effect. Tests that need fast slow-loop execution (e.g. `test_collector_status_updated_every_60s`, `test_disk_snapshots_written_every_60s`) should set this env var in their fixture.

### 4.1 Python Test Framework

- **Framework:** pytest
- **Plugins:** `pytest-mock` (for monkeypatching), `pytest-tmp-files` or built-in `tmp_path`
- **Config file:** `claw-collector/pytest.ini` or `pyproject.toml` section
- **Fixtures:**
  - `test_db`: Creates a temp SQLite DB, runs `schema.sql`, yields connection, cleans up
  - `mock_proc`: Sets up a fake `/proc` tree in a temp directory, monkeypatches all `open()` calls for `/proc/...`
  - `mock_pynvml`: Patches all pynvml functions with sensible defaults

### 4.2 Next.js Test Framework

- **Framework:** Vitest (preferred over Jest for Next.js App Router compatibility)
- **Config file:** `web/vitest.config.ts`
- **Key configuration:**
  ```ts
  import { defineConfig } from "vitest/config";
  import path from "path";
  export default defineConfig({
    test: { environment: "node" },
    resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  });
  ```
- **Fixtures:**
  - `testDb()`: Creates in-memory better-sqlite3 DB, runs `schema.sql`, mocks `@/lib/db` `getDb()` to return it
  - Helper: `makeRequest(method, url, body?)` — constructs a `NextRequest` and calls the route handler directly (no HTTP server needed for unit tests)
- **SSE tests:** Use Playwright or a raw `fetch()` against a running dev server for SSE streaming tests (these are integration tests, not unit tests)

### 4.3 DB Isolation

Every test must use a temporary SQLite DB. No test may hardcode `~/.openclaw/claw-monitor/metrics.db`.

**Prerequisite code changes (must be done before tests can run):**
- `claw-collector/config.py` must read `CM_DB_PATH` from env with default:
  ```python
  DB_PATH = os.environ.get("CM_DB_PATH", os.path.expanduser("~/.openclaw/claw-monitor/metrics.db"))
  ```
- `web/src/lib/db.ts` must read `CM_DB_PATH` from env with default:
  ```ts
  const DB_PATH = process.env.CM_DB_PATH
    ?? path.join(os.homedir(), ".openclaw", "claw-monitor", "metrics.db");
  ```

**Unit tests (Python):** pytest fixture creates `tmp_path / "test.db"`, passes via `CM_DB_PATH` env var or monkeypatches `config.DB_PATH`:
```python
@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("config.DB_PATH", db_path)
    conn = open_db()
    init_schema(conn)
    yield conn
    conn.close()
```

**Unit tests (Vitest):** Each test gets a fresh in-memory better-sqlite3 DB (`:memory:`) via `vi.mock("@/lib/db")`.

**Integration tests:** Shared file-based DB per test session, created in `/tmp/claw-test-<uuid>/metrics.db`, passed via `CM_DB_PATH` env var to both collector and web subprocesses.

**Schema init:** All test DBs are initialized by executing `schema.sql`.

**No shared state:** Unit tests must not depend on ordering or share DB handles.

### 4.4 Port Isolation

Integration tests that start a web server must bind to a random or alternate port — never the default production port.

**Prerequisite code change:**
- The web app must read `CM_PORT` from env. See §3c of the port placeholder changes — `web/claw-web.service` and `web/package.json` must use `${CM_PORT:-7432}`.

**Test strategy:**
- Integration test fixtures pick a random free port (e.g. `get_free_port()` helper) or use a fixed test port like `CM_PORT=17432`.
- No test hardcodes port `7432`.
- The test harness starts the web server with `CM_PORT=<test-port>` and all HTTP requests target `http://localhost:<test-port>`.

```python
@pytest.fixture
def web_server(test_db_path):
    port = find_free_port()  # bind to port 0, read assigned port
    proc = subprocess.Popen(
        ["npm", "--prefix", "web", "run", "dev"],
        env={**os.environ, "CM_DB_PATH": test_db_path, "CM_PORT": str(port)},
    )
    yield f"http://localhost:{port}"
    proc.terminate()
```

### 4.5 Collector Isolation

Integration tests that start the collector must point it at the test DB and must NOT interfere with the live collector.

**Rules:**
- Start the collector as a subprocess with `CM_DB_PATH` env var pointing to the test DB.
- Never restart, stop, or interact with the `claw-collector` systemd service from tests.
- The systemd service uses the default DB path — tests use a different path, so there is no conflict.

```python
@pytest.fixture
def collector(test_db_path):
    proc = subprocess.Popen(
        ["python3", "claw-collector/collector.py"],
        env={**os.environ, "CM_DB_PATH": test_db_path},
    )
    yield proc
    proc.terminate()
    proc.wait(timeout=5)
```

**Important:** Tests must NOT call `systemctl --user restart claw-collector` — this would disrupt the live production collector.

### 4.6 Parallel Safety

Tests must be safe to run multiple times concurrently:
- Each test run uses its own temp DB (different `tmp_path` / UUID).
- Each integration test run binds to its own random port.
- No test writes to shared filesystem locations (e.g. `~/.openclaw/`).

**Tests that cannot be parallelised:**
- `/proc`-based integration tests that depend on the real process tree (e.g. `test_collector_finds_openclaw_gateway_pid`, `test_cpu_percent_matches_top`) — these read global system state and may see each other's subprocesses. Mark with `@pytest.mark.serial` and exclude from `pytest-xdist` parallel runs.
- SSE integration tests that start a web server — safe if each uses a different port (handled by random port allocation above).

**pytest-xdist:** Unit tests can run in parallel. Integration tests should use `--dist=no` or be marked `@pytest.mark.serial`.

### 4.7 Mock Strategy — pynvml

- **Unit tests:** Always mock. Use `unittest.mock.patch("gpu_tracker.pynvml")` or `pytest-mock`
- **GPU present:** Mock returns realistic values (util=45%, VRAM=4GB, power=150W)
- **GPU absent:** Mock `nvmlInit` raises `Exception`; all tests for graceful fallback
- **CI:** pynvml may not even be importable. Mock at import level or skip GPU tests with `@pytest.mark.skipif(not HAS_PYNVML, reason="pynvml not installed")`

### 4.8 Mock Strategy — `/proc`

- **Unit tests:** Never read real `/proc`. Use monkeypatched `open()` or fixture-created temp files
- **Integration/functional tests:** Read real `/proc` — this is the point of these tests
- **Fixture pattern for unit tests:**
  ```python
  @pytest.fixture
  def fake_proc(tmp_path, monkeypatch):
      proc_dir = tmp_path / "proc"
      proc_dir.mkdir()
      # Helper to create fake /proc/<pid>/stat etc.
      def create_pid(pid, comm="python3", utime=1000, stime=500, vmrss_kb=102400):
          pid_dir = proc_dir / str(pid)
          pid_dir.mkdir()
          (pid_dir / "comm").write_text(f"{comm}\n")
          # ... write stat, status, cmdline files
      # Monkeypatch open() to redirect /proc/ reads to tmp_path/proc/
      original_open = builtins.open
      def patched_open(path, *args, **kwargs):
          if isinstance(path, str) and path.startswith("/proc/"):
              path = str(proc_dir / path[6:])  # strip "/proc/"
          return original_open(path, *args, **kwargs)
      monkeypatch.setattr("builtins.open", patched_open)
      return create_pid
  ```

### 4.9 CI Considerations

- **GPU tests:** Mark with `@pytest.mark.gpu`. CI config skips this marker unless runner has NVIDIA GPU
- **`/proc` tests:** Unit tests use mocks (run anywhere). Integration tests only run on Linux
- **better-sqlite3:** Requires native compilation. CI needs `build-essential` and `python3`
- **Port conflicts:** Integration tests use random ports via `CM_PORT` env var (see §4.4) — never the default production port
- **Timeouts:** SSE tests need generous timeouts (45s for ping test). Set `pytest --timeout=60` for integration tests
- **Parallelism:** Unit tests can run in parallel (`pytest-xdist`). Integration tests that read `/proc` should be serial (see §4.6)

---

## 5. Coverage Targets

### 5.1 Line Coverage Goals

| Component | Target | Rationale |
|---|---|---|
| `pid_tracker.py` | 95% | Core logic, many edge cases, fully mockable |
| `net_tracker.py` | 100% | Small module, fully testable |
| `gpu_tracker.py` | 90% | Exception paths hard to trigger; mock covers most |
| `disk_tracker.py` | 90% | Real filesystem tests cover main paths |
| `db.py` | 95% | All DB operations critical; test with real SQLite |
| `collector.py` | 80% | Main loop and signal handling hard to unit-test; integration tests cover the rest |
| `config.py` | N/A | Constants only, no logic to test |
| API routes (all) | 95% | All request/response paths testable via direct handler calls |
| `middleware.ts` | 100% | Security-critical, small, fully testable |
| `lib/cost.ts` | 100% | Pure function, trivial to test |
| `lib/db.ts` | 80% | Singleton pattern; test init path |
| Components (`.tsx`) | 0% | Presentational only; visual testing out of scope |

### 5.2 Must-Have 100% Coverage Paths

These paths are critical and must have complete test coverage:

1. **`resolveTs()` in `/api/tags/route.ts`** — all 5 input formats plus null/invalid. Backdating correctness is a user-facing feature.
2. **`isTailscaleOrLocal()` in `middleware.ts`** — security boundary. Every IP range boundary must be tested.
3. **`estimateCost()` in `lib/cost.ts`** — financial calculation, must match pricing.json exactly.
4. **`verify_pid()` in `pid_tracker.py`** — PID reuse detection prevents attributing metrics to wrong process.
5. **Write-gate threshold logic** — the `ACTIVITY_THRESHOLD_PCT` comparison. Wrong threshold = silent data loss or DB bloat.
6. **`NetTracker.get_delta()`** — delta math including first-call and counter-wrap edge cases.

### 5.3 Acceptable to Skip

- **GPU tests on non-NVIDIA CI** — mark with `@pytest.mark.gpu`, skip when `pynvml` import fails
- **SSE streaming in unit tests** — cover in integration tests with real HTTP
- **React components** — no business logic; visual correctness validated by manual QA
- **`get_journald_size()`** — depends on systemd; mock in unit tests, verify manually
- **Signal handler (`handle_signal`)** — tested indirectly via integration; hard to unit-test cleanly
- **Slow loop thread lifecycle** — integration test verifies it runs; unit-testing threading is fragile

---

## Appendix: Test File Layout

```
claw-monitor/
  claw-collector/
    tests/
      conftest.py          # fixtures: test_db, fake_proc, mock_pynvml
      test_pid_tracker.py
      test_net_tracker.py
      test_gpu_tracker.py
      test_disk_tracker.py
      test_db.py
      test_collector.py    # CpuTracker, sync_processes, write-gate
  web/
    vitest.config.ts
    tests/
      helpers.ts           # testDb(), makeRequest() helpers
      tags.test.ts
      tokens.test.ts
      metrics.test.ts
      metrics-stream.test.ts
      disk.test.ts
      tokens-summary.test.ts
      registry.test.ts
      middleware.test.ts
      cost.test.ts
  tests/
    integration/
      conftest.py          # service start/stop, test DB setup
      test_collector_live.py
      test_api_live.py
      test_e2e_scripts.py
      test_sse_live.py
      test_backdate.py
```
