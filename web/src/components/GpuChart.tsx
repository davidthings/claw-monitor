"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

interface DataPoint {
  ts: number;
  gpu_util_pct?: number;
  gpu_vram_used_mb?: number;
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function GpuChart({ data }: { data: DataPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
        <XAxis dataKey="ts" type="number" scale="time" domain={["auto", "auto"]} tickFormatter={formatTime} stroke="#888" />
        <YAxis yAxisId="pct" unit="%" stroke="#888" />
        <YAxis yAxisId="mb" orientation="right" unit="MB" stroke="#888" />
        <Tooltip
          labelFormatter={(v) => formatTime(v as number)}
          contentStyle={{ background: "#1a1a2e", border: "1px solid #333" }}
        />
        <Legend />
        <Line yAxisId="pct" type="monotone" dataKey="gpu_util_pct" name="GPU %" stroke="#a855f7" dot={false} />
        <Line yAxisId="mb" type="monotone" dataKey="gpu_vram_used_mb" name="VRAM MB" stroke="#ec4899" dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
