PRAGMA journal_mode=WAL;

-- Fast-loop time-series (written ONLY when OpenClaw activity detected)
CREATE TABLE IF NOT EXISTS metrics (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ts                INTEGER NOT NULL,
  grp               TEXT NOT NULL,
  cpu_pct           REAL,
  mem_rss_mb        REAL,
  net_in_kb         REAL,
  net_out_kb        REAL,
  gpu_util_pct      REAL,
  gpu_vram_used_mb  REAL,
  gpu_power_w       REAL,
  sample_interval_s INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);
CREATE INDEX IF NOT EXISTS idx_metrics_grp_ts ON metrics(grp, ts);

-- Single-row collector liveness (always UPDATE, never INSERT after init)
CREATE TABLE IF NOT EXISTS collector_status (
  id         INTEGER PRIMARY KEY CHECK (id = 1),
  last_seen  INTEGER NOT NULL,
  started_at INTEGER NOT NULL
);

-- Daily aggregates (retained forever)
CREATE TABLE IF NOT EXISTS metrics_daily (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  date           TEXT NOT NULL,
  grp            TEXT NOT NULL,
  avg_cpu_pct    REAL,
  max_cpu_pct    REAL,
  avg_mem_rss_mb REAL,
  max_mem_rss_mb REAL,
  sum_net_in_kb  REAL,
  sum_net_out_kb REAL,
  avg_gpu_pct    REAL,
  max_gpu_pct    REAL,
  max_vram_mb    REAL,
  UNIQUE(date, grp)
);

-- Disk space snapshots (every 60s regardless of activity)
CREATE TABLE IF NOT EXISTS disk_snapshots (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER NOT NULL,
  dir_key     TEXT NOT NULL,
  size_bytes  INTEGER NOT NULL,
  file_count  INTEGER,
  journald_mb REAL
);
CREATE INDEX IF NOT EXISTS idx_disk_ts ON disk_snapshots(ts);

-- Registered processes
CREATE TABLE IF NOT EXISTS process_registry (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  pid          INTEGER NOT NULL,
  name         TEXT NOT NULL,
  grp          TEXT NOT NULL,
  description  TEXT,
  registered   INTEGER NOT NULL,
  unregistered INTEGER
);
CREATE INDEX IF NOT EXISTS idx_registry_pid ON process_registry(pid);

-- Token usage events
CREATE TABLE IF NOT EXISTS token_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         INTEGER NOT NULL,
  tool       TEXT NOT NULL,
  model      TEXT NOT NULL,
  tokens_in  INTEGER,
  tokens_out INTEGER,
  session_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_token_events_ts ON token_events(ts);
CREATE INDEX IF NOT EXISTS idx_token_events_tool ON token_events(tool);

-- Work-type annotations
CREATE TABLE IF NOT EXISTS tags (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts          INTEGER NOT NULL,      -- effective timestamp (may be backdated)
  recorded_at INTEGER NOT NULL,      -- wall-clock time tag was actually submitted; ts != recorded_at means backdated
  category    TEXT NOT NULL,
  text        TEXT NOT NULL,
  source      TEXT NOT NULL,
  session_id  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tags_ts ON tags(ts);
