"use client";

import { useEffect, useState, useCallback } from "react";
import CpuAreaChart from "@/components/CpuAreaChart";
import GpuChart from "@/components/GpuChart";
import NetworkChart from "@/components/NetworkChart";

interface MetricRow {
  ts: number;
  grp: string;
  cpu_pct?: number;
  mem_rss_mb?: number;
  net_in_kb?: number;
  net_out_kb?: number;
  gpu_util_pct?: number;
  gpu_vram_used_mb?: number;
}

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<MetricRow[]>([]);
  const [range, setRange] = useState(3600); // 1 hour default
  const [resolution, setResolution] = useState("auto");

  const fetchData = useCallback(async () => {
    const now = Math.floor(Date.now() / 1000);
    const from = now - range;
    const res = await fetch(`/api/metrics?from=${from}&to=${now}&resolution=${resolution}`);
    const data = await res.json();
    setMetrics(data.data || []);
  }, [range, resolution]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const cpuByTs: Record<number, Record<string, number>> = {};
  const memByTs: Record<number, Record<string, number>> = {};
  const gpuData: { ts: number; gpu_util_pct?: number; gpu_vram_used_mb?: number }[] = [];
  const netData: { ts: number; net_in_kb?: number; net_out_kb?: number }[] = [];

  for (const row of metrics) {
    if (row.grp === "gpu") {
      gpuData.push({ ts: row.ts, gpu_util_pct: row.gpu_util_pct, gpu_vram_used_mb: row.gpu_vram_used_mb });
    } else if (row.grp === "net") {
      netData.push({ ts: row.ts, net_in_kb: row.net_in_kb, net_out_kb: row.net_out_kb });
    } else {
      if (!cpuByTs[row.ts]) cpuByTs[row.ts] = { ts: row.ts };
      cpuByTs[row.ts][row.grp] = row.cpu_pct || 0;
      if (!memByTs[row.ts]) memByTs[row.ts] = { ts: row.ts };
      memByTs[row.ts][row.grp] = row.mem_rss_mb || 0;
    }
  }

  const cpuData = Object.values(cpuByTs).sort((a, b) => a.ts - b.ts);
  const memData = Object.values(memByTs).sort((a, b) => a.ts - b.ts);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h1 style={{ fontSize: 20, fontWeight: 700 }}>Time-Series Explorer</h1>
        <div style={{ display: "flex", gap: 8 }}>
          {[
            { label: "30m", val: 1800 },
            { label: "1h", val: 3600 },
            { label: "6h", val: 21600 },
            { label: "24h", val: 86400 },
            { label: "7d", val: 604800 },
          ].map((r) => (
            <button
              key={r.val}
              onClick={() => setRange(r.val)}
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
          <select
            value={resolution}
            onChange={(e) => setResolution(e.target.value)}
            style={{ background: "#1a1a2e", color: "#e2e8f0", border: "1px solid #333", borderRadius: 4, padding: "4px 8px", fontSize: 12 }}
          >
            <option value="auto">Auto</option>
            <option value="raw">Raw</option>
            <option value="hourly">Hourly</option>
            <option value="daily">Daily</option>
          </select>
        </div>
      </div>

      <div className="card">
        <h2>CPU by Group</h2>
        <CpuAreaChart data={cpuData} />
      </div>

      <div className="card">
        <h2>Memory by Group</h2>
        <CpuAreaChart data={memData} />
      </div>

      <div className="card">
        <h2>GPU</h2>
        <GpuChart data={gpuData} />
      </div>

      <div className="card">
        <h2>Network</h2>
        <NetworkChart data={netData} />
      </div>

      <p style={{ color: "#94a3b8", fontSize: 12, marginTop: 8 }}>
        {metrics.length} data points loaded
      </p>
    </div>
  );
}
