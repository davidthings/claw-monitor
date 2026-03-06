"use client";

import { useEffect, useState, useCallback } from "react";
import LiveIndicator from "@/components/LiveIndicator";
import CombinedChart from "@/components/CombinedChart";
import CostBadge from "@/components/CostBadge";

interface MetricRow {
  ts: number;
  grp: string;
  cpu_pct?: number;
  mem_rss_mb?: number;
  net_in_kb?: number;
  net_out_kb?: number;
  gpu_util_pct?: number;
  gpu_vram_used_mb?: number;
  gpu_power_w?: number;
}

interface Tag {
  id: number;
  ts: number;
  recorded_at?: number;
  category: string;
  text: string;
  source: string;
}

interface TokenTotals {
  tokens_in: number;
  tokens_out: number;
  calls: number;
  est_cost_usd: number;
}

interface DiskRow {
  dir_key: string;
  size_bytes: number;
}

interface ChartPoint {
  ts: number;
  cpu?: number;
  mem?: number;
  gpu?: number;
  net?: number;
  tokens?: number;
}

const RANGE_OPTIONS = [
  { label: "30m", val: 1800 },
  { label: "1h", val: 3600 },
  { label: "2h", val: 7200 },
  { label: "6h", val: 21600 },
  { label: "24h", val: 86400 },
  { label: "7d", val: 604800 },
];

const STORAGE_KEY = "claw-overview-range";

function getInitialRange(): number {
  if (typeof window === "undefined") return 7200;
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) {
    const n = Number(saved);
    if (RANGE_OPTIONS.some((r) => r.val === n)) return n;
  }
  return 7200;
}

function rollingAverage(arr: (number | undefined)[], window: number): (number | undefined)[] {
  return arr.map((_, i) => {
    const start = Math.max(0, i - window + 1);
    let sum = 0;
    let count = 0;
    for (let j = start; j <= i; j++) {
      if (arr[j] != null) {
        sum += arr[j]!;
        count++;
      }
    }
    return count > 0 ? sum / count : undefined;
  });
}

function pivotMetrics(metrics: MetricRow[]): ChartPoint[] {
  const byTs: Record<number, { cpu: number; mem: number; gpu?: number; net?: number }> = {};

  for (const row of metrics) {
    if (!byTs[row.ts]) byTs[row.ts] = { cpu: 0, mem: 0 };
    const entry = byTs[row.ts];

    if (row.grp === "gpu") {
      entry.gpu = row.gpu_util_pct ?? undefined;
    } else if (row.grp === "net") {
      entry.net = (row.net_in_kb || 0) + (row.net_out_kb || 0);
    } else {
      entry.cpu += (row.cpu_pct || 0) / 100;
      entry.mem = Math.max(entry.mem, (row.mem_rss_mb || 0) / 1024);
    }
  }

  return Object.entries(byTs)
    .map(([ts, v]) => ({ ts: Number(ts), ...v }))
    .sort((a, b) => a.ts - b.ts);
}

function mergeTokens(chartData: ChartPoint[], tokenEvents: { ts: number; total: number }[]): ChartPoint[] {
  if (tokenEvents.length === 0) return chartData;

  // Determine bucket size from chart data
  let bucketSize = 60;
  if (chartData.length >= 2) {
    const diffs: number[] = [];
    for (let i = 1; i < Math.min(chartData.length, 20); i++) {
      diffs.push(chartData[i].ts - chartData[i - 1].ts);
    }
    diffs.sort((a, b) => a - b);
    bucketSize = Math.max(diffs[Math.floor(diffs.length / 2)], 1);
  }

  // Bucket token events
  const tokenBuckets: Record<number, number> = {};
  for (const ev of tokenEvents) {
    const bucket = Math.floor(ev.ts / bucketSize) * bucketSize;
    tokenBuckets[bucket] = (tokenBuckets[bucket] || 0) + ev.total;
  }

  // Convert to tok/min
  const bucketMinutes = bucketSize / 60;
  for (const k of Object.keys(tokenBuckets)) {
    tokenBuckets[Number(k)] = tokenBuckets[Number(k)] / Math.max(bucketMinutes, 1);
  }

  // Apply rolling average (window=3)
  const bucketKeys = Object.keys(tokenBuckets).map(Number).sort((a, b) => a - b);
  const rawVals = bucketKeys.map((k) => tokenBuckets[k]);
  const smoothed = rollingAverage(rawVals, 3);
  const smoothedMap: Record<number, number> = {};
  bucketKeys.forEach((k, i) => {
    if (smoothed[i] != null) smoothedMap[k] = smoothed[i]!;
  });

  // Merge into chart data by finding closest bucket
  return chartData.map((pt) => {
    const bucket = Math.floor(pt.ts / bucketSize) * bucketSize;
    const tokVal = smoothedMap[bucket];
    return tokVal != null ? { ...pt, tokens: tokVal } : pt;
  });
}

export default function HomePage() {
  const [metrics, setMetrics] = useState<MetricRow[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [tokenTotals, setTokenTotals] = useState<TokenTotals | null>(null);
  const [tokenRate, setTokenRate] = useState(0);
  const [disk, setDisk] = useState<DiskRow[]>([]);
  const [tokenEvents, setTokenEvents] = useState<{ ts: number; total: number }[]>([]);
  const [range, setRange] = useState(getInitialRange);

  const handleRangeChange = useCallback((val: number) => {
    setRange(val);
    localStorage.setItem(STORAGE_KEY, String(val));
  }, []);

  const fetchData = useCallback(async () => {
    const now = Math.floor(Date.now() / 1000);
    const from = now - range;

    const [mRes, tRes, tkRes, dRes, rateRes, tevRes] = await Promise.all([
      fetch(`/api/metrics?from=${from}&to=${now}&resolution=auto`),
      fetch(`/api/tags?from=${from}&to=${now}`),
      fetch(`/api/tokens/summary?from=${now - 86400}&to=${now}`),
      fetch(`/api/disk?from=${now - 300}&to=${now}`),
      fetch(`/api/tokens/rate`),
      fetch(`/api/tokens?from=${from}&to=${now}`),
    ]);

    const [mData, tData, tkData, dData, rateData, tevData] = await Promise.all([
      mRes.json(),
      tRes.json(),
      tkRes.json(),
      dRes.json(),
      rateRes.json(),
      tevRes.json(),
    ]);

    setMetrics(mData.data || []);
    setTags(tData.tags || []);
    setTokenTotals(tkData.totals || null);
    setTokenRate(rateData.rate || 0);

    // Token events for chart
    const events = (tevData.data || tevData.events || []) as Array<{ ts: number; tokens_in?: number; tokens_out?: number }>;
    setTokenEvents(
      events.map((e) => ({
        ts: e.ts,
        total: (e.tokens_in || 0) + (e.tokens_out || 0),
      }))
    );

    const dRows = dData.data || [];
    const latestDisk: Record<string, DiskRow> = {};
    for (const r of dRows) {
      if (!latestDisk[r.dir_key]) latestDisk[r.dir_key] = r;
    }
    setDisk(Object.values(latestDisk));
  }, [range]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Pivot metrics for combined chart
  const chartData = pivotMetrics(metrics);
  const chartWithTokens = mergeTokens(chartData, tokenEvents);

  // Summary stats from latest timestamp
  const latestTs = metrics.reduce((max, r) => Math.max(max, r.ts), 0);
  const latestRows = metrics.filter((r) => r.ts === latestTs && r.grp !== "gpu" && r.grp !== "net");
  const latestCpuCores = latestRows.reduce((sum, r) => sum + (r.cpu_pct || 0), 0) / 100;
  const latestMemMb = latestRows.reduce((sum, r) => sum + (r.mem_rss_mb || 0), 0);

  let latestGpu = 0;
  let latestVram = 0;
  for (const row of metrics) {
    if (row.ts === latestTs && row.grp === "gpu") {
      if (row.gpu_util_pct != null) latestGpu = row.gpu_util_pct;
      if (row.gpu_vram_used_mb != null) latestVram = row.gpu_vram_used_mb;
    }
  }

  const totalDiskMb = disk.reduce((sum, d) => {
    if (d.dir_key === "openclaw-total") return d.size_bytes / (1024 * 1024);
    return sum;
  }, 0);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700 }}>CLAW MONITOR</h1>
          <p style={{ fontSize: 12, color: "#94a3b8" }}>to help right-size the machine</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <LiveIndicator />
          {tokenTotals && <CostBadge cost={tokenTotals.est_cost_usd} />}
        </div>
      </div>

      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>CPU</h2>
          <div className="stat-value">{latestCpuCores.toFixed(2)} cores</div>
          <div className="stat-label">OpenClaw total (now)</div>
        </div>
        <div className="card">
          <h2>Memory</h2>
          <div className="stat-value">{(latestMemMb / 1024).toFixed(2)}GB</div>
          <div className="stat-label">of 64GB RSS (now)</div>
        </div>
        <div className="card">
          <h2>GPU</h2>
          <div className="stat-value">{latestGpu.toFixed(0)}%</div>
          <div className="stat-label">{(latestVram / 1024).toFixed(1)}GB VRAM</div>
        </div>
        <div className="card">
          <h2>Disk</h2>
          <div className="stat-value">{totalDiskMb.toFixed(0)}MB</div>
          <div className="stat-label">openclaw total</div>
        </div>
        <div className="card">
          <h2>Tokens</h2>
          <div className="stat-value">{tokenRate} tok/min</div>
          <div className="stat-label">current rate</div>
        </div>
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <h2>Resource Overview</h2>
          <div style={{ display: "flex", gap: 6 }}>
            {RANGE_OPTIONS.map((r) => (
              <button
                key={r.val}
                onClick={() => handleRangeChange(r.val)}
                style={{
                  padding: "4px 10px",
                  background: range === r.val ? "#3b82f6" : "#1a1a2e",
                  color: range === r.val ? "#fff" : "#94a3b8",
                  border: "1px solid #333",
                  borderRadius: 4,
                  cursor: "pointer",
                  fontSize: 12,
                }}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>
        <CombinedChart data={chartWithTokens} tags={tags} rangeSeconds={range} />
      </div>
    </div>
  );
}
