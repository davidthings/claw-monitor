"use client";

import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

interface Props {
  data: Record<string, number>[];
  groups?: string[];
}

const GROUP_COLORS: Record<string, string> = {
  "openclaw-core": "#3b82f6",
  "openclaw-browser": "#f59e0b",
  "openclaw-agent": "#10b981",
};

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function CpuAreaChart({ data, groups = ["openclaw-core", "openclaw-browser", "openclaw-agent"] }: Props) {
  return (
    <ResponsiveContainer width="100%" height={250}>
      <AreaChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="#333" />
        <XAxis dataKey="ts" type="number" scale="time" domain={["auto", "auto"]} tickFormatter={formatTime} stroke="#888" />
        <YAxis unit="%" stroke="#888" />
        <Tooltip
          labelFormatter={(v) => formatTime(v as number)}
          contentStyle={{ background: "#1a1a2e", border: "1px solid #333" }}
        />
        <Legend />
        {groups.map((g) => (
          <Area
            key={g}
            type="monotone"
            dataKey={g}
            stackId="cpu"
            fill={GROUP_COLORS[g] || "#888"}
            stroke={GROUP_COLORS[g] || "#888"}
            fillOpacity={0.6}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
