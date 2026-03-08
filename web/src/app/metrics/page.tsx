"use client";

import { useEffect, useState, useCallback } from "react";
import CpuAreaChart from "@/components/CpuAreaChart";
import GpuChart from "@/components/GpuChart";
import NetworkChart from "@/components/NetworkChart";
import DiskTimeChart from "@/components/DiskTimeChart";
import TokensChart from "@/components/TokensChart";

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

interface DiskRow {
  ts: number;
  dir_key: string;
  size_bytes: number;
}

interface TokenEvent {
  ts: number;
  tokens_in: number;
  tokens_out: number;
}

interface Tag {
  id: number;
  ts: number;
  category: string;
  text: string;
  source: string;
}

const TAG_COLORS: Record<string, string> = {
  conversation: "#38bdf8",
  coding: "#f59e0b",
  research: "#14b8a6",
  agent: "#a855f7",
  heartbeat: "#6b7280",
  qwen: "#84cc16",
  idle: "#374151",
  other: "#e2e8f0",
};

export default function MetricsPage() {
  const [metrics, setMetrics] = useState<MetricRow[]>([]);
  const [diskData, setDiskData] = useState<{ ts: number; size_mb: number }[]>([]);
  const [tokensData, setTokensData] = useState<{ ts: number; tok_per_min: number }[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [range, setRange] = useState(3600); // 1 hour default
  const [resolution, setResolution] = useState("auto");

  const fetchData = useCallback(async () => {
    const now = Math.floor(Date.now() / 1000);
    const from = now - range;

    const [metricsRes, diskRes, tokensRes, tagsRes] = await Promise.all([
      fetch(`/api/metrics?from=${from}&to=${now}&resolution=${resolution}`),
      fetch(`/api/disk?from=${from}&to=${now}`),
      fetch(`/api/tokens?from=${from}&to=${now}`),
      fetch(`/api/tags?from=${from}&to=${now}`),
    ]);

    const metricsJson = await metricsRes.json();
    setMetrics(metricsJson.data || []);

    // Disk: filter to openclaw-total, convert to MB, sort by time
    const diskJson = await diskRes.json();
    const diskRows = (diskJson.data || []) as DiskRow[];
    setDiskData(
      diskRows
        .filter((r: DiskRow) => r.dir_key === "openclaw-total")
        .map((r: DiskRow) => ({ ts: r.ts, size_mb: r.size_bytes / 1024 / 1024 }))
        .sort((a: { ts: number }, b: { ts: number }) => a.ts - b.ts)
    );

    // Tokens: bucket into 1-minute bins, compute tokens/min, rolling avg window=3
    const tokensJson = await tokensRes.json();
    const events = (tokensJson.events || []) as TokenEvent[];
    const buckets: Record<number, number> = {};
    for (const e of events) {
      const bucket = Math.floor(e.ts / 60) * 60;
      buckets[bucket] = (buckets[bucket] || 0) + (e.tokens_in || 0) + (e.tokens_out || 0);
    }
    const sorted = Object.entries(buckets)
      .map(([ts, count]) => ({ ts: Number(ts), tok_per_min: count }))
      .sort((a, b) => a.ts - b.ts);
    // Rolling average window=3
    const smoothed = sorted.map((pt, i) => {
      const start = Math.max(0, i - 1);
      const end = Math.min(sorted.length - 1, i + 1);
      let sum = 0;
      let cnt = 0;
      for (let j = start; j <= end; j++) {
        sum += sorted[j].tok_per_min;
        cnt++;
      }
      return { ts: pt.ts, tok_per_min: Math.round(sum / cnt) };
    });
    setTokensData(smoothed);

    // Tags
    const tagsJson = await tagsRes.json();
    setTags((tagsJson.tags || []) as Tag[]);
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
      cpuByTs[row.ts][row.grp] = (row.cpu_pct || 0) / 100; // % → cores
      if (!memByTs[row.ts]) memByTs[row.ts] = { ts: row.ts };
      memByTs[row.ts][row.grp] = (row.mem_rss_mb || 0) / 1024; // MB → GB
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
        <CpuAreaChart data={cpuData} unit="cores" decimals={2} />
      </div>

      <div className="card">
        <h2>Memory by Group</h2>
        <CpuAreaChart data={memData} unit="GB" decimals={2} />
      </div>

      <div className="card">
        <h2>GPU</h2>
        <GpuChart data={gpuData} />
      </div>

      <div className="card">
        <h2>Network</h2>
        <NetworkChart data={netData} />
      </div>

      <div className="card">
        <h2>Disk (openclaw-total)</h2>
        <DiskTimeChart data={diskData} />
      </div>

      <div className="card">
        <h2>Tokens/min</h2>
        <TokensChart data={tokensData} />
      </div>

      <div className="card">
        <h2>Tags</h2>
        {(() => {
          const sorted = [...tags].sort((a, b) => a.ts - b.ts);
          const now = Math.floor(Date.now() / 1000);
          const from = now - range;
          return (
            <div style={{ position: "relative", height: 80, background: "#0f0f1a", borderRadius: 4 }}>
              {sorted.map((tag) => {
                const pct = ((tag.ts - from) / range) * 100;
                if (pct < 0 || pct > 100) return null;
                const color = TAG_COLORS[tag.category] || TAG_COLORS.other;
                const time = new Date(tag.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                return (
                  <div
                    key={tag.id}
                    style={{
                      position: "absolute",
                      left: `${pct}%`,
                      top: 0,
                      bottom: 0,
                      width: 12,            // wide hover target
                      transform: "translateX(-6px)",
                      cursor: "pointer",
                      zIndex: 1,
                    }}
                    onMouseEnter={(e) => {
                      const tip = e.currentTarget.querySelector(".tag-tip") as HTMLElement;
                      if (tip) tip.style.display = "block";
                    }}
                    onMouseLeave={(e) => {
                      const tip = e.currentTarget.querySelector(".tag-tip") as HTMLElement;
                      if (tip) tip.style.display = "none";
                    }}
                  >
                    {/* visible 2px tick */}
                    <div style={{
                      position: "absolute",
                      left: 5,
                      top: 0,
                      bottom: 0,
                      width: 2,
                      background: color,
                      opacity: 0.85,
                    }} />
                    {/* tooltip */}
                    <div className="tag-tip" style={{
                      display: "none",
                      position: "absolute",
                      bottom: "100%",
                      left: "50%",
                      transform: "translateX(-50%)",
                      background: "#1e1e2e",
                      border: `1px solid ${color}`,
                      borderRadius: 4,
                      padding: "4px 8px",
                      whiteSpace: "nowrap",
                      fontSize: 11,
                      color: "#e2e8f0",
                      pointerEvents: "none",
                      zIndex: 100,
                      marginBottom: 4,
                    }}>
                      <span style={{ color, fontWeight: 700 }}>{tag.category}</span>
                      {" · "}{time}
                      <br />
                      {tag.text}
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })()}
      </div>

      <p style={{ color: "#94a3b8", fontSize: 12, marginTop: 8 }}>
        {metrics.length} data points loaded
      </p>
    </div>
  );
}
