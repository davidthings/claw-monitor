"use client";

import { useEffect, useState, useCallback } from "react";
import LiveIndicator from "@/components/LiveIndicator";
import CpuAreaChart from "@/components/CpuAreaChart";
import GpuChart from "@/components/GpuChart";
import NetworkChart from "@/components/NetworkChart";
import TagLog from "@/components/TagLog";
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

export default function HomePage() {
  const [metrics, setMetrics] = useState<MetricRow[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [tokenTotals, setTokenTotals] = useState<TokenTotals | null>(null);
  const [disk, setDisk] = useState<DiskRow[]>([]);

  const fetchData = useCallback(async () => {
    const now = Math.floor(Date.now() / 1000);
    const from = now - 1800; // last 30 min

    const [mRes, tRes, tkRes, dRes] = await Promise.all([
      fetch(`/api/metrics?from=${from}&to=${now}`),
      fetch(`/api/tags?from=${from}&to=${now}`),
      fetch(`/api/tokens/summary?from=${now - 86400}&to=${now}`),
      fetch(`/api/disk?from=${now - 300}&to=${now}`),
    ]);

    const mData = await mRes.json();
    const tData = await tRes.json();
    const tkData = await tkRes.json();
    const dData = await dRes.json();

    setMetrics(mData.data || []);
    setTags(tData.tags || []);
    setTokenTotals(tkData.totals || null);

    // Get latest disk snapshot per dir_key
    const dRows = dData.data || [];
    const latestDisk: Record<string, DiskRow> = {};
    for (const r of dRows) {
      if (!latestDisk[r.dir_key]) latestDisk[r.dir_key] = r;
    }
    setDisk(Object.values(latestDisk));
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Transform metrics for charts
  const cpuByTs: Record<number, Record<string, number>> = {};
  const gpuData: { ts: number; gpu_util_pct?: number; gpu_vram_used_mb?: number }[] = [];
  const netData: { ts: number; net_in_kb?: number; net_out_kb?: number }[] = [];

  let latestCpu = 0, latestMem = 0, latestGpu = 0, latestVram = 0;

  for (const row of metrics) {
    if (row.grp === "gpu") {
      gpuData.push({ ts: row.ts, gpu_util_pct: row.gpu_util_pct, gpu_vram_used_mb: row.gpu_vram_used_mb });
      if (row.gpu_util_pct != null) latestGpu = row.gpu_util_pct;
      if (row.gpu_vram_used_mb != null) latestVram = row.gpu_vram_used_mb;
    } else if (row.grp === "net") {
      netData.push({ ts: row.ts, net_in_kb: row.net_in_kb, net_out_kb: row.net_out_kb });
    } else {
      if (!cpuByTs[row.ts]) cpuByTs[row.ts] = { ts: row.ts };
      cpuByTs[row.ts][row.grp] = row.cpu_pct || 0;
      if (row.cpu_pct != null) latestCpu += row.cpu_pct;
      if (row.mem_rss_mb != null) latestMem += row.mem_rss_mb;
    }
  }
  const cpuChartData = Object.values(cpuByTs).sort((a, b) => a.ts - b.ts);

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
        <LiveIndicator />
      </div>

      <div className="stat-grid" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>CPU</h2>
          <div className="stat-value">{latestCpu.toFixed(0)}%</div>
          <div className="stat-label">OpenClaw total</div>
        </div>
        <div className="card">
          <h2>Memory</h2>
          <div className="stat-value">{(latestMem / 1024).toFixed(1)}GB</div>
          <div className="stat-label">of 64GB</div>
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
      </div>

      <div className="card">
        <h2>CPU by Group — Last 30 min</h2>
        <CpuAreaChart data={cpuChartData} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card">
          <h2>GPU — Last 30 min</h2>
          <GpuChart data={gpuData} />
        </div>
        <div className="card">
          <h2>Network — Last 30 min</h2>
          <NetworkChart data={netData} />
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card">
          <h2>Recent Tags</h2>
          <TagLog tags={tags.slice(0, 10)} />
        </div>
        <div className="card">
          <h2>Today&apos;s Token Usage</h2>
          {tokenTotals ? (
            <div>
              <div className="stat-value" style={{ fontSize: 18 }}>
                {(tokenTotals.tokens_in / 1000).toFixed(0)}K in / {(tokenTotals.tokens_out / 1000).toFixed(0)}K out
              </div>
              <div style={{ marginTop: 4 }}>
                {tokenTotals.calls} calls <CostBadge cost={tokenTotals.est_cost_usd} />
              </div>
            </div>
          ) : (
            <p style={{ color: "#888" }}>No token data today</p>
          )}
        </div>
      </div>
    </div>
  );
}
