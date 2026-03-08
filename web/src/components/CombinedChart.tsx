"use client";

import { useMemo, useState, useRef, useCallback } from "react";
import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

const TAG_COLORS: Record<string, string> = {
  conversation: "#38bdf8",
  coding: "#fbbf24",
  research: "#2dd4bf",
  agent: "#a78bfa",
  heartbeat: "#6b7280",
  qwen: "#a3e635",
  idle: "#374151",
  other: "#e5e7eb",
};

interface Tag {
  id: number;
  ts: number;
  category: string;
  text: string;
}

interface ChartPoint {
  ts: number;
  cpu?: number;
  mem?: number;
  gpu?: number;
  net?: number;
  tokens?: number;
}

interface TagCluster {
  ts: number;
  tags: Tag[];
  category: string; // primary category (first tag's)
}

interface Props {
  data: ChartPoint[];
  tags: Tag[];
  rangeSeconds: number;
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTimeFull(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function clusterTags(tags: Tag[], rangeSeconds: number, chartWidth: number): TagCluster[] {
  if (tags.length === 0) return [];
  const threshold = (rangeSeconds / Math.max(chartWidth, 1)) * 8;
  const sorted = [...tags].sort((a, b) => a.ts - b.ts);
  const clusters: TagCluster[] = [];
  let current: TagCluster = { ts: sorted[0].ts, tags: [sorted[0]], category: sorted[0].category };

  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i].ts - current.ts <= threshold) {
      current.tags.push(sorted[i]);
    } else {
      clusters.push(current);
      current = { ts: sorted[i].ts, tags: [sorted[i]], category: sorted[i].category };
    }
  }
  clusters.push(current);
  return clusters;
}

interface TagLabelProps {
  viewBox?: { x: number; y: number; width?: number; height?: number };
  color: string;
  count: number;
  cluster: TagCluster;
  onHover: (cluster: TagCluster | null, x: number, y: number) => void;
}

function TagLabel({ viewBox, color, count, cluster, onHover }: TagLabelProps) {
  if (!viewBox) return null;
  const { x } = viewBox;
  return (
    <g
      onMouseEnter={(e) => onHover(cluster, e.clientX, e.clientY)}
      onMouseLeave={() => onHover(null, 0, 0)}
      style={{ cursor: "pointer" }}
    >
      <polygon
        points={`${x - 5},${0} ${x + 5},${0} ${x},${8}`}
        fill={color}
        opacity={0.9}
      />
      {count > 1 && (
        <text x={x} y={-4} textAnchor="middle" fill="#e2e8f0" fontSize={9} fontWeight={600}>
          {count}
        </text>
      )}
    </g>
  );
}

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ dataKey: string; value: number }>; label?: number }) {
  if (!active || !payload || !label) return null;
  const vals: Record<string, number | undefined> = {};
  for (const p of payload) {
    vals[p.dataKey] = p.value;
  }

  const fmt = (key: string, v: number | undefined, unit: string, decimals = 2) => {
    if (v == null || isNaN(v)) return "\u2014";
    return `${v.toFixed(decimals)} ${unit}`;
  };

  return (
    <div style={{
      background: "#1a1a2e",
      border: "1px solid #333",
      borderRadius: 6,
      padding: "8px 12px",
      fontSize: 12,
      color: "#e2e8f0",
      lineHeight: 1.6,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{formatTimeFull(label)}</div>
      <div><span style={{ color: "#4ade80" }}>CPU</span>{"      "}{fmt("cpu", vals.cpu, "cores")}</div>
      <div><span style={{ color: "#60a5fa" }}>Memory</span>{"   "}{fmt("mem", vals.mem, "GB")}</div>
      <div><span style={{ color: "#e879f9" }}>GPU</span>{"      "}{fmt("gpu", vals.gpu, "%", 0)}</div>
      <div><span style={{ color: "#fb923c" }}>Network</span>{"  "}{fmt("net", vals.net, "KB/s", 0)}</div>
      <div><span style={{ color: "#facc15" }}>Tokens</span>{"   "}{fmt("tokens", vals.tokens, "tok/min", 0)}</div>
    </div>
  );
}

export default function CombinedChart({ data, tags, rangeSeconds }: Props) {
  const [hoveredCluster, setHoveredCluster] = useState<{ cluster: TagCluster; x: number; y: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(800);

  const onResize = useCallback((w: number) => {
    setChartWidth(w);
  }, []);

  const clusters = useMemo(
    () => clusterTags(tags, rangeSeconds, chartWidth),
    [tags, rangeSeconds, chartWidth]
  );

  const handleTagHover = useCallback((cluster: TagCluster | null, x: number, y: number) => {
    if (cluster) {
      setHoveredCluster({ cluster, x, y });
    } else {
      setHoveredCluster(null);
    }
  }, []);

  return (
    <div ref={containerRef} style={{ position: "relative" }}>
      <ResponsiveContainer width="100%" height={350} onResize={onResize}>
        <ComposedChart data={data} margin={{ top: 20, right: 60, left: 20, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#333" />
          <XAxis
            dataKey="ts"
            type="number"
            scale="time"
            domain={[
              () => Math.floor(Date.now() / 1000) - rangeSeconds,
              () => Math.floor(Date.now() / 1000),
            ]}
            tickFormatter={formatTime}
            stroke="#888"
          />
          <YAxis
            yAxisId="left"
            stroke="#888"
            label={{ value: "cores / GB", angle: -90, position: "insideLeft", fill: "#888", fontSize: 11 }}
          />
          <YAxis
            yAxisId="right"
            orientation="right"
            stroke="#888"
            label={{ value: "% / KB/s / tok/min", angle: 90, position: "insideRight", fill: "#888", fontSize: 11 }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          <Line yAxisId="left" type="monotone" dataKey="cpu" stroke="#4ade80" dot={false} name="CPU (cores)" strokeWidth={1.5} />
          <Line yAxisId="left" type="monotone" dataKey="mem" stroke="#60a5fa" dot={false} name="Memory (GB)" strokeWidth={1.5} />
          <Line yAxisId="right" type="monotone" dataKey="gpu" stroke="#e879f9" dot={false} name="GPU (%)" strokeWidth={1.5} />
          <Line yAxisId="right" type="monotone" dataKey="net" stroke="#fb923c" dot={false} name="Network (KB/s)" strokeWidth={1.5} />
          <Line yAxisId="right" type="monotone" dataKey="tokens" stroke="#facc15" dot={false} name="Tokens (tok/min)" strokeWidth={1.5} />
          {clusters.map((c, i) => (
            <ReferenceLine
              key={i}
              x={c.ts}
              yAxisId="left"
              stroke={TAG_COLORS[c.category] || TAG_COLORS.other}
              strokeWidth={2}
              strokeDasharray="4 2"
              label={
                <TagLabel
                  color={TAG_COLORS[c.category] || TAG_COLORS.other}
                  count={c.tags.length}
                  cluster={c}
                  onHover={handleTagHover}
                />
              }
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>

      {hoveredCluster && (
        <div
          style={{
            position: "fixed",
            left: hoveredCluster.x + 12,
            top: hoveredCluster.y - 10,
            background: "#1a1a2e",
            border: "1px solid #444",
            borderRadius: 6,
            padding: "8px 12px",
            fontSize: 12,
            color: "#e2e8f0",
            zIndex: 1000,
            maxWidth: 320,
            pointerEvents: "none",
          }}
        >
          {hoveredCluster.cluster.tags.map((t, i) => (
            <div key={t.id || i} style={{ marginBottom: i < hoveredCluster.cluster.tags.length - 1 ? 4 : 0 }}>
              <span style={{ color: "#888" }}>{formatTime(t.ts)}</span>{" "}
              <span
                style={{
                  background: TAG_COLORS[t.category] || TAG_COLORS.other,
                  color: "#000",
                  borderRadius: 3,
                  padding: "1px 5px",
                  fontSize: 10,
                  fontWeight: 600,
                }}
              >
                {t.category}
              </span>{" "}
              <span>{t.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
